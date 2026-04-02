"""Validate subagent-generated certificates and format into training data.

Reads batch results from both train and test splits, validates each certificate
structurally (Pass 0 + strength check, no Hypothesis), and writes passing
results to data/training/training_data.jsonl.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certus.pipeline.collector import CodeSample
from certus.pipeline.augmenter import AugmentationResult
from certus.pipeline.validator import validate_augmentation
from certus.pipeline.formatter import format_validated_results


def load_split(
    results_dir: Path, batches_dir: Path, label: str
) -> list[AugmentationResult]:
    """Load a single split from its results and batches dirs."""
    results = []
    batch_files = sorted(results_dir.glob("batch_*_results.json"))

    for batch_file in batch_files:
        with open(batch_file) as f:
            batch_data = json.load(f)

        batch_num = batch_file.stem.split("_")[1]
        input_file = batches_dir / f"batch_{batch_num}.json"
        with open(input_file) as f:
            input_data = json.load(f)

        samples_by_id = {s["task_id"]: s for s in input_data}

        for item in batch_data:
            task_id = str(item["task_id"])
            sample_data = samples_by_id.get(task_id)
            if sample_data is None:
                print(
                    f"  WARNING: task_id {task_id} not found in {label} batch {batch_num}"
                )
                continue

            sample = CodeSample(
                source=sample_data["source"],
                task_id=task_id,
                description=sample_data["description"],
                code=sample_data["code"],
                test_code=sample_data.get("test_code"),
            )

            aug = AugmentationResult(
                sample=sample,
                certificate_kwargs=item.get("certificate_kwargs"),
                raw_response=item.get("raw_response", ""),
                error=item.get("error"),
            )
            results.append(aug)

    return results


def main():
    output_dir = Path("data/training")
    output_dir.mkdir(parents=True, exist_ok=True)

    aug_results = []

    # Load train split
    train_results = Path("data/results_train")
    train_batches = Path("data/batches_train")
    if train_results.exists():
        print("Loading train split results...")
        train = load_split(train_results, train_batches, "train")
        print(f"  Train: {len(train)} samples")
        aug_results.extend(train)

    # Load test split
    test_results = Path("data/results")
    test_batches = Path("data/batches")
    if test_results.exists() and any(test_results.glob("batch_*_results.json")):
        print("Loading test split results...")
        test = load_split(test_results, test_batches, "test")
        print(f"  Test: {len(test)} samples")
        aug_results.extend(test)

    print(f"Total: {len(aug_results)} augmentation results")

    # Count how many have certificates vs errors
    has_cert = sum(1 for a in aug_results if a.certificate_kwargs is not None)
    has_error = sum(1 for a in aug_results if a.error is not None)
    print(f"  With certificates: {has_cert}")
    print(f"  With errors: {has_error}")

    # Validate using structural mode (no Hypothesis)
    print("\nValidating certificates (structural mode)...")
    validated = []
    pass_count = 0
    fail_reasons = {}

    for i, aug in enumerate(aug_results):
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        validated.append(vr)
        if vr.passed:
            pass_count += 1
        else:
            reason = vr.reason or "unknown"
            key = reason.split(":")[0] if ":" in reason else reason
            fail_reasons[key] = fail_reasons.get(key, 0) + 1

        if (i + 1) % 100 == 0:
            print(f"  Validated {i + 1}/{len(aug_results)} ({pass_count} passing)")

    print(f"\nValidation complete: {pass_count}/{len(aug_results)} passed")
    print("Failure reasons:")
    for reason, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    # Format passing results
    print("\nFormatting training examples...")
    passed = [v for v in validated if v.passed]
    examples = format_validated_results(passed)
    print(
        f"Generated {len(examples)} training examples ({len(examples) // 2} Task A + {len(examples) // 2} Task B)"
    )

    # Write JSONL
    output_file = output_dir / "training_data.jsonl"
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict()) + "\n")
    print(f"Written to {output_file}")

    # Write report
    report = {
        "total_samples": len(aug_results),
        "with_certificates": has_cert,
        "with_errors": has_error,
        "validation_passed": pass_count,
        "validation_failed": len(aug_results) - pass_count,
        "training_examples": len(examples),
        "pass_rate": round(pass_count / max(len(aug_results), 1), 4),
        "failure_reasons": fail_reasons,
    }
    report_file = output_dir / "report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report written to {report_file}")


if __name__ == "__main__":
    main()
