"""Collect MBPP samples and split into batch files for subagent processing."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certus.pipeline.collector import MBPPCollector


def main():
    max_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    num_batches = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    split = sys.argv[3] if len(sys.argv) > 3 else "train"

    print(f"Collecting up to {max_samples} MBPP samples from '{split}' split...")
    collector = MBPPCollector(max_samples=max_samples, split=split)
    samples = collector.collect()
    print(f"Collected {len(samples)} samples")

    batch_dir = Path("data/batches")
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_size = (len(samples) + num_batches - 1) // num_batches
    for i in range(num_batches):
        batch = samples[i * batch_size : (i + 1) * batch_size]
        if not batch:
            break

        batch_data = []
        for s in batch:
            batch_data.append(
                {
                    "task_id": s.task_id,
                    "source": s.source,
                    "description": s.description,
                    "code": s.code,
                    "test_code": s.test_code,
                }
            )

        out_path = batch_dir / f"batch_{i}.json"
        with open(out_path, "w") as f:
            json.dump(batch_data, f, indent=2)

        print(f"  Batch {i}: {len(batch)} samples -> {out_path}")

    # Also save a manifest
    manifest = {
        "total_samples": len(samples),
        "num_batches": num_batches,
        "batch_size": batch_size,
    }
    with open(batch_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print("Done.")


if __name__ == "__main__":
    main()
