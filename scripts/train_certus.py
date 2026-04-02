"""Certus certificate generation finetuning script.

QLoRA finetuning of Qwen 2.5 Coder 7B using Unsloth + SFTTrainer.
Designed to run standalone on a machine with 16GB VRAM.

Usage:
    uv run scripts/train_certus.py [--data DATA_PATH] [--output OUTPUT_DIR] [--epochs N]

Requires: unsloth, trl, datasets, torch (see requirements-train.txt)
"""

import argparse
import json
import torch
from pathlib import Path


def load_training_data(data_path: str) -> list[dict]:
    """Load training examples from JSONL file."""
    examples = []
    with open(data_path) as f:
        for line in f:
            ex = json.loads(line)
            examples.append(ex)
    return examples


def main():
    parser = argparse.ArgumentParser(
        description="Finetune Qwen 2.5 Coder 7B for Certus certificate generation"
    )
    parser.add_argument(
        "--data",
        default="data/training/training_data.jsonl",
        help="Path to training JSONL",
    )
    parser.add_argument(
        "--output",
        default="models/certus-qwen-7b-lora",
        help="Output directory for LoRA adapters",
    )
    parser.add_argument(
        "--epochs", type=int, default=3, help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size", type=int, default=2, help="Per-device batch size"
    )
    parser.add_argument(
        "--grad-accum", type=int, default=4, help="Gradient accumulation steps"
    )
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument(
        "--max-seq-length", type=int, default=2048, help="Maximum sequence length"
    )
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument(
        "--base-model",
        default="unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
        help="Base model name or path",
    )
    args = parser.parse_args()

    # --- 1. Load model ---
    print(f"Loading {args.base_model} (4-bit)...")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,  # auto-detect
        load_in_4bit=True,
    )

    # --- 2. Configure LoRA ---
    print(f"Applying LoRA adapters (r={args.lora_r})...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_r,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # --- 3. Set up chat template (Qwen 2.5 uses ChatML) ---
    from unsloth import get_chat_template

    tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

    # --- 4. Load and format dataset ---
    print(f"Loading training data from {args.data}...")
    raw_examples = load_training_data(args.data)
    print(f"  Loaded {len(raw_examples)} examples")

    # Convert to the format SFTTrainer expects: a "text" field with the
    # formatted chat template applied.
    formatted = []
    for ex in raw_examples:
        messages = ex["messages"]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        formatted.append({"text": text})

    from datasets import Dataset

    dataset = Dataset.from_list(formatted)
    print(f"  Dataset size: {len(dataset)} examples")

    # --- 5. Configure training ---
    from trl import SFTTrainer, SFTConfig

    training_args = SFTConfig(
        output_dir=args.output,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        optim="adamw_8bit",
        weight_decay=0.01,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        save_strategy="epoch",
        seed=3407,
        max_seq_length=args.max_seq_length,
        dataset_text_field="text",
        packing=True,
    )

    # --- 6. Set up trainer with response-only loss ---
    from unsloth import train_on_responses_only

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    # Only compute loss on assistant responses, not user prompts
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    # --- 7. Train ---
    print("\nStarting training...")
    print(f"  Epochs: {args.epochs}")
    print(f"  Effective batch size: {args.batch_size * args.grad_accum}")
    print(f"  Learning rate: {args.lr}")
    print(f"  LoRA rank: {args.lora_r}")
    stats = trainer.train()
    print(f"\nTraining complete. Final loss: {stats.training_loss:.4f}")

    # --- 8. Save LoRA adapters ---
    print(f"\nSaving LoRA adapters to {args.output}...")
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)

    # Verify saved tensors aren't empty
    from safetensors import safe_open

    adapter_path = Path(args.output) / "adapter_model.safetensors"
    if adapter_path.exists():
        with safe_open(str(adapter_path), framework="pt") as f:
            for key in f.keys():
                tensor = f.get_tensor(key)
                n_zeros = (tensor == 0).sum().item()
                assert n_zeros != tensor.numel(), f"Tensor {key} is all zeros!"
        print("  Adapter verification passed (non-zero weights)")

    print(f"\nDone. To use the model:")
    print(f"  from unsloth import FastLanguageModel")
    print(f"  model, tokenizer = FastLanguageModel.from_pretrained('{args.output}')")


if __name__ == "__main__":
    main()
