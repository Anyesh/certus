"""Quick inference script to test the finetuned Certus model.

Uses standard transformers (no unsloth fast path) to avoid inference bugs.

Usage:
    uv run scripts/infer_certus.py [--model MODEL_PATH] [--task-a | --task-b] CODE

Examples:
    # Task B: generate certificate for existing code
    uv run scripts/infer_certus.py --task-b "def add(a, b): return a + b"

    # Task A: generate code + certificate from description
    uv run scripts/infer_certus.py --task-a "Write a function to check if a number is prime"
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Certus certificate inference")
    parser.add_argument("input", help="Code (task B) or description (task A)")
    parser.add_argument(
        "--model", default="models/certus-qwen-7b-lora", help="Model path"
    )
    parser.add_argument(
        "--task-a",
        action="store_true",
        help="Task A: description -> code + certificate",
    )
    parser.add_argument(
        "--task-b", action="store_true", help="Task B: code -> certificate (default)"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=1024, help="Max tokens to generate"
    )
    args = parser.parse_args()

    if not args.task_a:
        args.task_b = True

    # Use standard transformers + peft instead of unsloth for inference
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    import torch

    print(f"Loading model from {args.model}...")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        quantization_config=quant_config,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base_model, args.model)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    # Set model to inference mode
    model.config.use_cache = True
    model.generation_config.do_sample = True

    if args.task_b:
        prompt = f"Generate a Certus certificate for this function:\n\n{args.input}"
    else:
        prompt = args.input

    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=args.max_tokens,
            temperature=0.1,
            top_p=0.95,
            do_sample=True,
        )

    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
    )
    print("\n" + response)


if __name__ == "__main__":
    main()
