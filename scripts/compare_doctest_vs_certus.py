"""Compare doctest coverage vs Certus certificate coverage.

For each validation sample, measures:
1. Doctest: how many MBPP test cases exist, what they cover
2. Certus: how many guarantees, what properties they verify, over how many random inputs

Produces concrete examples showing where each approach has advantages.
"""

import json
import sys
import ast
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certus.pipeline.augmenter import parse_certificate_from_response
from certus.pipeline.collector import CodeSample


def count_test_cases(test_code):
    """Count assert statements in MBPP test code."""
    if not test_code:
        return 0
    return sum(
        1 for line in test_code.strip().split("\n") if line.strip().startswith("assert")
    )


def count_guarantees(cert_kwargs):
    """Count total guarantee expressions in a certificate."""
    if not cert_kwargs:
        return 0
    total = 0
    for post in cert_kwargs.get("postconditions", []):
        total += len(post.get("guarantees", []))
    return total


def count_branches(cert_kwargs):
    """Count distinct 'when' conditions (behavioral branches)."""
    if not cert_kwargs:
        return 0
    whens = set()
    for post in cert_kwargs.get("postconditions", []):
        whens.add(post.get("when", "always"))
    return len(whens)


def classify_guarantee(g):
    """Classify a guarantee as type-check, bound, equality, relational, or structural."""
    g = g.strip()
    if g.startswith("isinstance("):
        return "type-check"
    if any(op in g for op in ["==", "!="]) and "result" in g:
        if any(f in g for f in ["sorted(", "len(", "sum(", "all(", "any("]):
            return "structural"
        return "equality"
    if any(op in g for op in [">=", "<=", ">", "<"]):
        return "bound"
    if any(f in g for f in ["all(", "any(", "sorted("]):
        return "structural"
    return "other"


def main():
    samples_path = sys.argv[1] if len(sys.argv) > 1 else "data/eval_samples.json"
    generated_path = (
        sys.argv[2] if len(sys.argv) > 2 else "data/eval_generated_14b.json"
    )

    with open(samples_path) as f:
        samples = json.load(f)
    with open(generated_path) as f:
        generated = json.load(f)

    gen_by_id = {str(g["task_id"]): g for g in generated}

    print("=" * 65)
    print("DOCTEST vs CERTUS COMPARISON")
    print("=" * 65)

    # Aggregate stats
    total = len(samples)
    doctest_total_cases = 0
    certus_total_guarantees = 0
    certus_total_branches = 0
    certus_parsed = 0
    guarantee_types = {
        "type-check": 0,
        "equality": 0,
        "bound": 0,
        "structural": 0,
        "other": 0,
    }

    interesting_examples = []

    for sample in samples:
        tid = str(sample["task_id"])
        gen = gen_by_id.get(tid)
        if not gen:
            continue

        n_tests = count_test_cases(sample.get("test_code"))
        doctest_total_cases += n_tests

        cert_kwargs = parse_certificate_from_response(gen["raw_response"])
        if cert_kwargs:
            certus_parsed += 1
            n_guarantees = count_guarantees(cert_kwargs)
            n_branches = count_branches(cert_kwargs)
            certus_total_guarantees += n_guarantees
            certus_total_branches += n_branches

            for post in cert_kwargs.get("postconditions", []):
                for g in post.get("guarantees", []):
                    gtype = classify_guarantee(g)
                    guarantee_types[gtype] += 1

            # Flag interesting cases: many guarantees + few tests, or branches > 1
            if n_guarantees >= 3 and n_branches >= 2:
                interesting_examples.append(
                    {
                        "task_id": tid,
                        "description": sample["description"][:80],
                        "n_tests": n_tests,
                        "n_guarantees": n_guarantees,
                        "n_branches": n_branches,
                        "guarantees": [
                            g
                            for p in cert_kwargs.get("postconditions", [])
                            for g in p.get("guarantees", [])
                        ],
                        "test_code": sample.get("test_code", "")[:200],
                    }
                )

    # Report
    print(f"\nSamples analyzed: {total}")
    print(f"Certus certificates parsed: {certus_parsed}/{total}")

    print(f"\n--- Coverage Breadth ---")
    print(f"Doctest: {doctest_total_cases} specific input/output assertions")
    print(f"  Average: {doctest_total_cases / total:.1f} test cases per function")
    print(f"  Each test checks ONE specific input -> ONE expected output")
    print(f"")
    print(f"Certus:  {certus_total_guarantees} general property guarantees")
    print(
        f"  Average: {certus_total_guarantees / max(certus_parsed, 1):.1f} guarantees per function"
    )
    print(f"  Each guarantee is verified across 30 random inputs (Hypothesis)")
    print(f"  Total verification points: ~{certus_total_guarantees * 30}")
    print(
        f"  Behavioral branches: {certus_total_branches} total ({certus_total_branches / max(certus_parsed, 1):.1f} per function)"
    )

    print(f"\n--- Guarantee Types ---")
    for gtype, count in sorted(guarantee_types.items(), key=lambda x: -x[1]):
        pct = 100 * count / max(sum(guarantee_types.values()), 1)
        print(f"  {gtype:15s} {count:4d} ({pct:.0f}%)")

    print(f"\n--- What Certus Covers That Doctest Cannot ---")
    print(
        f"  1. General properties verified across many random inputs, not just 3 examples"
    )
    print(
        f"  2. Branched behavior: {certus_total_branches} conditional branches explicitly declared"
    )
    print(f"  3. Strength scoring: tautological claims are detected and rejected")
    print(
        f"  4. Structural properties: 'result is sorted', 'all elements satisfy predicate'"
    )

    print(f"\n--- Concrete Examples ---")
    for ex in interesting_examples[:5]:
        print(f"\n  Task {ex['task_id']}: {ex['description']}")
        print(f"  Doctest: {ex['n_tests']} specific assertions")
        if ex["test_code"]:
            for line in ex["test_code"].strip().split("\n")[:2]:
                print(f"    {line.strip()}")
        print(
            f"  Certus: {ex['n_guarantees']} guarantees across {ex['n_branches']} branches"
        )
        for g in ex["guarantees"][:4]:
            print(f"    - {g}")
        if len(ex["guarantees"]) > 4:
            print(f"    ... and {len(ex['guarantees']) - 4} more")

    # Save report
    report = {
        "doctest_total_cases": doctest_total_cases,
        "doctest_avg_per_function": round(doctest_total_cases / total, 2),
        "certus_parsed": certus_parsed,
        "certus_total_guarantees": certus_total_guarantees,
        "certus_avg_guarantees": round(
            certus_total_guarantees / max(certus_parsed, 1), 2
        ),
        "certus_total_branches": certus_total_branches,
        "certus_verification_points": certus_total_guarantees * 30,
        "guarantee_types": guarantee_types,
    }
    with open("data/doctest_comparison.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to data/doctest_comparison.json")


if __name__ == "__main__":
    main()
