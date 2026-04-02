"""Benchmark Certus on real-world utility functions with full timing.

Measures inference time, checker time, tokens generated, and end-to-end latency.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certus.generator import (
    extract_functions,
    call_inference_server,
    generate_for_function,
)


def count_tokens(text, approx_chars_per_token=4):
    """Rough token count estimate."""
    return len(text) // approx_chars_per_token


def main():
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8234"
    filepath = sys.argv[2] if len(sys.argv) > 2 else "examples/real_world.py"

    with open(filepath) as f:
        source = f.read()

    functions = extract_functions(source)
    print(f"Found {len(functions)} functions in {filepath}")
    print(f"Server: {server_url}")
    print()

    results = []
    total_inference_time = 0
    total_checker_time = 0
    total_tokens = 0

    for name, func_src in functions:
        print(f"--- {name} ---")

        # Measure inference time
        t0 = time.time()
        raw = call_inference_server(func_src, server_url)
        t_inference = time.time() - t0

        if raw is None:
            print(f"  SKIP: inference failed")
            results.append({"function": name, "status": "inference_failed"})
            continue

        total_inference_time += t_inference
        tokens = count_tokens(raw)
        total_tokens += tokens
        tps = tokens / t_inference if t_inference > 0 else 0

        print(f"  inference: {t_inference:.1f}s ({tokens} tokens, {tps:.1f} tok/s)")

        # Measure checker time
        t1 = time.time()
        result = generate_for_function(
            name, func_src, source, server_url, checker_mode="fast", num_runs=30
        )
        t_total = time.time() - t0
        # Checker time = total minus the second inference call (which we already did)
        # Actually let's just time the full generate_for_function which includes inference + check
        # Re-measure properly
        t_checker = time.time() - t1 - t_inference  # subtract the inference portion

        passed = result.validation.passed if result.validation else False
        status = "PASS" if passed else "FAIL"

        if result.error:
            status = f"ERROR: {result.error}"
        elif result.validation and not result.validation.passed:
            status = f"FAIL: {result.validation.reason}"

        print(f"  check:     {t_total - t_inference:.1f}s")
        print(f"  total:     {t_total:.1f}s")
        print(f"  result:    {status}")
        if result.raw_certificate:
            # Show first 2 lines of certificate
            cert_lines = result.raw_certificate.strip().split("\n")
            for line in cert_lines[:3]:
                print(f"  cert:      {line}")
            if len(cert_lines) > 3:
                print(f"  cert:      ... ({len(cert_lines)} lines total)")
        print()

        total_checker_time += max(0, t_total - t_inference)
        results.append(
            {
                "function": name,
                "status": "pass" if passed else "fail",
                "inference_time": round(t_inference, 2),
                "total_time": round(t_total, 2),
                "tokens_generated": tokens,
                "tokens_per_second": round(tps, 1),
                "certificate_lines": len(result.raw_certificate.strip().split("\n"))
                if result.raw_certificate
                else 0,
            }
        )

    # Summary
    passed = sum(1 for r in results if r.get("status") == "pass")
    total = len(results)
    print("=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Functions:        {total}")
    print(f"Passed:           {passed}/{total} ({100 * passed / max(total, 1):.0f}%)")
    print(
        f"Inference time:   {total_inference_time:.1f}s total ({total_inference_time / max(total, 1):.1f}s avg)"
    )
    print(
        f"Checker time:     {total_checker_time:.1f}s total ({total_checker_time / max(total, 1):.1f}s avg)"
    )
    print(
        f"End-to-end:       {total_inference_time + total_checker_time:.1f}s total ({(total_inference_time + total_checker_time) / max(total, 1):.1f}s avg)"
    )
    print(f"Tokens generated: {total_tokens} ({total_tokens / max(total, 1):.0f} avg)")
    print(
        f"Throughput:       {total_tokens / max(total_inference_time, 0.1):.1f} tokens/sec"
    )
    print()

    with open("data/benchmark_results.json", "w") as f:
        json.dump(
            {
                "functions": results,
                "summary": {
                    "total": total,
                    "passed": passed,
                    "total_inference_time": round(total_inference_time, 2),
                    "total_checker_time": round(total_checker_time, 2),
                    "total_tokens": total_tokens,
                    "tokens_per_second": round(
                        total_tokens / max(total_inference_time, 0.1), 1
                    ),
                },
            },
            f,
            indent=2,
        )
    print("Saved to data/benchmark_results.json")


if __name__ == "__main__":
    main()
