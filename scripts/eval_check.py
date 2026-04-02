"""Evaluate model-generated certificates through the full Certus checker.

Reads eval_generated.json (raw model outputs) and eval_samples.json (source code),
parses certificates, runs through structural + dynamic verification, reports metrics.

Usage:
    python scripts/eval_check.py [--generated eval_generated.json] [--samples eval_samples.json]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certus.pipeline.augmenter import (
    parse_certificate_from_response,
    AugmentationResult,
)
from certus.pipeline.collector import CodeSample
from certus.pipeline.validator import validate_augmentation


def main():
    generated_path = sys.argv[1] if len(sys.argv) > 1 else "data/eval_generated.json"
    samples_path = sys.argv[2] if len(sys.argv) > 2 else "data/eval_samples.json"

    with open(generated_path) as f:
        generated = json.load(f)
    with open(samples_path) as f:
        samples = json.load(f)

    samples_by_id = {str(s["task_id"]): s for s in samples}
    print(f"Loaded {len(generated)} model outputs, {len(samples)} samples\n")

    # --- Metrics ---
    total = len(generated)
    parsed = 0
    structural_pass = 0
    dynamic_pass = 0
    tautological = 0
    failures = {
        "parse_failed": [],
        "structural_failed": [],
        "dynamic_failed": [],
        "tautological": [],
    }

    for item in generated:
        task_id = str(item["task_id"])
        raw = item["raw_response"]
        sample_data = samples_by_id.get(task_id)
        if not sample_data:
            continue

        sample = CodeSample(
            source=sample_data["source"],
            task_id=task_id,
            description=sample_data["description"],
            code=sample_data["code"],
            test_code=sample_data.get("test_code"),
        )

        # Step 1: Parse
        cert_kwargs = parse_certificate_from_response(raw)
        if cert_kwargs is None:
            failures["parse_failed"].append({"task_id": task_id, "raw": raw[:200]})
            continue
        parsed += 1

        aug = AugmentationResult(
            sample=sample,
            certificate_kwargs=cert_kwargs,
            raw_response=raw,
        )

        # Step 2: Structural validation (Pass 0 + strength, no Hypothesis)
        vr_structural = validate_augmentation(
            aug, num_runs=50, checker_mode="structural"
        )
        if not vr_structural.passed:
            reason = vr_structural.reason or "unknown"
            if "Tautological" in reason:
                tautological += 1
                failures["tautological"].append({"task_id": task_id, "reason": reason})
            else:
                failures["structural_failed"].append(
                    {"task_id": task_id, "reason": reason}
                )
            continue
        structural_pass += 1

        # Step 3: Full dynamic verification (Hypothesis, reduced runs)
        vr_dynamic = validate_augmentation(aug, num_runs=30, checker_mode="fast")
        if vr_dynamic.passed:
            dynamic_pass += 1
        else:
            reason = vr_dynamic.reason or "unknown"
            if "Tautological" in reason:
                tautological += 1
                failures["tautological"].append({"task_id": task_id, "reason": reason})
            else:
                failures["dynamic_failed"].append(
                    {"task_id": task_id, "reason": reason}
                )

    # --- Report ---
    print("=" * 60)
    print("CERTUS MODEL EVALUATION REPORT")
    print("=" * 60)
    print(f"\nTotal samples:           {total}")
    print(f"Parse success:           {parsed}/{total} ({100 * parsed / total:.1f}%)")
    print(
        f"Structural pass:         {structural_pass}/{total} ({100 * structural_pass / total:.1f}%)"
    )
    print(
        f"Dynamic (Hypothesis):    {dynamic_pass}/{total} ({100 * dynamic_pass / total:.1f}%)"
    )
    print(
        f"Tautological:            {tautological}/{total} ({100 * tautological / total:.1f}%)"
    )

    print(f"\n--- Failure Breakdown ---")
    print(f"Parse failures:          {len(failures['parse_failed'])}")
    print(f"Structural failures:     {len(failures['structural_failed'])}")
    print(f"Dynamic failures:        {len(failures['dynamic_failed'])}")
    print(f"Tautological:            {len(failures['tautological'])}")

    if failures["parse_failed"]:
        print(f"\n--- Parse Failures (first 5) ---")
        for f_item in failures["parse_failed"][:5]:
            print(f"  task {f_item['task_id']}: {f_item['raw'][:100]}...")

    if failures["structural_failed"]:
        print(f"\n--- Structural Failures (first 5) ---")
        for f_item in failures["structural_failed"][:5]:
            print(f"  task {f_item['task_id']}: {f_item['reason']}")

    if failures["dynamic_failed"]:
        print(f"\n--- Dynamic Failures (first 5) ---")
        for f_item in failures["dynamic_failed"][:5]:
            print(f"  task {f_item['task_id']}: {f_item['reason']}")

    # Save full report
    report = {
        "total": total,
        "parsed": parsed,
        "parse_rate": round(parsed / total, 4),
        "structural_pass": structural_pass,
        "structural_rate": round(structural_pass / total, 4),
        "dynamic_pass": dynamic_pass,
        "dynamic_rate": round(dynamic_pass / total, 4),
        "tautological": tautological,
        "tautological_rate": round(tautological / total, 4),
        "failures": failures,
    }
    report_path = Path(generated_path).parent / "eval_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {report_path}")


if __name__ == "__main__":
    main()
