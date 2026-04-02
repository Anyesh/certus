"""Batch inference for evaluation: generate certificates for all validation samples.

Uses Unsloth for fast loading and patched attention, but skips the buggy
fast_forward_inference path by not calling for_inference().

Usage:
    python eval_generate.py --model MODEL_PATH --input eval_samples.json --output eval_generated.json
"""

import argparse
import json
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Path to LoRA adapter dir")
    parser.add_argument("--input", required=True, help="Path to eval_samples.json")
    parser.add_argument("--output", required=True, help="Path for output JSON")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument(
        "--base-model",
        default=None,
        help="Base model (auto-detected from adapter config if omitted)",
    )
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel

    # Auto-detect base model from adapter config if not specified
    base_model = args.base_model
    if base_model is None:
        from pathlib import Path

        config_path = Path(args.model) / "adapter_config.json"
        if config_path.exists():
            with open(config_path) as f:
                cfg = json.load(f)
            base_model = cfg.get("base_model_name_or_path")
            print(f"Auto-detected base model: {base_model}")
    if base_model is None:
        base_model = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"

    print(f"Loading {base_model}...")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16
    )
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=quant_config,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, args.model)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model.config.use_cache = True

    with open(args.input) as f:
        samples = json.load(f)
    print(f"Loaded {len(samples)} samples")

    results = []
    start = time.time()

    for i, sample in enumerate(samples):
        prompt = f"Generate a Certus certificate for this function:\n\n{sample['code']}"
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)

        outputs = model.generate(
            **inputs,
            max_new_tokens=args.max_tokens,
            temperature=0.1,
            top_p=0.95,
            do_sample=True,
            use_cache=True,
        )

        response = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )

        results.append(
            {
                "task_id": sample["task_id"],
                "raw_response": response,
            }
        )

        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            eta = (len(samples) - i - 1) / rate
            print(f"  {i + 1}/{len(samples)} ({rate:.2f} samples/sec, ETA {eta:.0f}s)")

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    elapsed = time.time() - start
    print(
        f"Done. {len(results)} certificates in {elapsed:.0f}s ({elapsed / len(results):.1f}s per sample)"
    )
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
