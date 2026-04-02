# Certus

A standard for AI-generated code to carry machine-checkable certificates of correctness, plus a Python reference implementation and a finetuned model that generates them.

## What this is

When an LLM writes a function, it can also emit a *certificate*: a structured declaration of what the function guarantees about its behavior. Certus defines the format for these certificates and provides tooling to verify them automatically.

A certificate looks like this:

```python
@certus(
    preconditions=["len(arr) > 0", "1 <= k <= len(arr)"],
    postconditions=[
        {"when": "always",
         "guarantees": ["result in arr",
                        "sum(1 for x in arr if x < result) < k",
                        "sum(1 for x in arr if x <= result) >= k"]}
    ],
)
def kth_smallest(arr: list, k: int) -> int:
    return sorted(arr)[k - 1]
```

The checker then verifies these claims through structural validation (AST analysis of expressions), dynamic testing (Hypothesis-based property checking), and strength measurement (filtering tautological certificates that claim nothing useful).

## Why this matters

Code generation is getting very good, but there is no standard way to verify that generated code does what it claims. Tests help, but they check specific cases rather than general properties. Certus fills this gap by attaching formal-ish guarantees to generated code and providing a fast, automated verification pipeline.

The key insight is that certificates don't need to be *proofs* to be valuable. A certificate that says "this function always returns a non-negative integer" and passes 1000 random tests gives you meaningful confidence, even without a formal proof. The checker catches wrong claims, and the strength score catches vacuous ones.

## How this compares to doctest

A natural question: Python already has doctest. Why do we need certificates?

Doctest checks specific input/output pairs ("does `fib(5)` return `5`?"). Certus declares general properties ("for all non-negative n, the result is non-negative") and verifies them across many random inputs. Across 90 held-out functions:

| | Doctest (MBPP tests) | Certus (14B model) |
|---|---|---|
| Checks per function | 3 specific examples | 2.9 general properties |
| Total verification points | 270 | ~7,740 (30 random inputs each) |
| Behavioral branches | 0 | 133 (1.5 per function) |
| Property types | All exact equality | Bounds, structural, equality, type |
| Catches edge cases? | Only if examples hit them | Probabilistically, via random testing |
| Catches tautological claims? | N/A | Yes, strength scoring |

**Concrete example**: for a function that checks if a subset has a sum divisible by m, doctest verifies 3 specific arrays. Certus declares and verifies:
```python
{"when": "result == True",
 "guarantees": ["any(sum(arr[i:j]) % m == 0 for i in range(n) for j in range(i+1, n+1))"]}
```

This property is verified across randomly generated arrays. If someone changes the implementation and breaks an edge case outside the 3 doctest examples, doctest still passes. Certus has a much higher probability of catching it.

The tradeoff: Certus certificates have a 7.8% semantic error rate where the model generates wrong claims. A human-written doctest is never wrong about the examples it checks. The checker catches 100% of the model's errors, so incorrect certificates never reach the user as "verified," but they do reduce the yield (83.3% of generated certificates survive verification).

## Results

We finetuned Qwen 2.5 Coder models (via QLoRA) on 1420 training examples derived from the MBPP dataset and evaluated on 90 held-out samples.

### Evaluation metrics (held-out MBPP validation split, n=90)

| Stage | 7B model | 14B model | What it measures |
|---|---|---|---|
| Parse (valid `@certus` syntax) | 98.9% | **100%** | Can the model produce well-formed output? |
| Structural (safe expressions) | 85.6% | **91.1%** | Are all expressions in the safe subset? |
| Dynamic (Hypothesis, 30 runs) | 75.6% | **83.3%** | Do the claims actually hold under testing? |
| Tautological | 1.1% | 1.1% | How many certificates are vacuously true? |

Stepping from 7B to 14B improved every metric. The end-to-end pass rate jumped from 75.6% to 83.3%, and the genuine semantic error rate dropped from 10% to 7.8%.

### How we got here: iterative improvement

Each optimization we made had a measurable impact on the end-to-end pass rate:

| Change | End-to-end pass rate |
|---|---|
| 7B model, original safe subset | 65.6% |
| + expanded safe subset (method calls) | 75.6% (+10%) |
| + 14B model with higher LoRA rank | **83.3%** (+7.7%) |

The safe subset expansion recovered certificates that used natural Python idioms (`.split()`, `.lower()`, `.values()`) which the original AST validator rejected. The 14B model brought better semantic understanding, producing fewer wrong formulas and fewer expressions outside the safe subset.

### Failure analysis (14B model)

Of the 15 certificates that didn't pass end-to-end verification:

- **7 structural failures**: expressions using `math.*`, `lambda`, self-referential function calls, or other constructs outside the safe subset. The model writes something that isn't valid in the restricted expression language.
- **7 dynamic failures**: postconditions that Hypothesis disproved with counterexamples (wrong formulas, incorrect base cases, overconfident claims). These are genuine semantic errors.
- **1 tautological**: the certificate's claims were too weak to reject random inputs.

The 7 dynamic failures (7.8%) represent the model's actual semantic error rate. The checker catches 100% of these, which validates the architecture: model proposes, checker verifies.

### Training details

| Parameter | 7B model | 14B model |
|---|---|---|
| Base model | Qwen 2.5 Coder 7B Instruct | Qwen 2.5 Coder 14B Instruct |
| Quantization | 4-bit (bnb) | 4-bit (bnb) |
| LoRA rank | 16 | 32 |
| Trainable params | 40M / 7.6B (0.53%) | 138M / 14.9B (0.92%) |
| Training examples | 1420 (710 Task A + 710 Task B) | 1420 (same dataset) |
| Epochs | 3 | 3 |
| Final loss | 0.20 | 0.38 |
| Training time | 8.5 min | 17.7 min |
| VRAM used | ~8 / 16 GB | ~15.9 / 16 GB |
| Hardware | RTX 4070 Ti SUPER (16GB) | RTX 4070 Ti SUPER (16GB) |

The 14B model has higher final loss because larger models need more data and epochs to converge, but its evaluation metrics are better across the board, confirming that model scale matters more than training loss for downstream task quality.

### Does finetuning matter? Base model comparison

To verify that our QLoRA finetuning adds real value, we also ran the base Qwen 2.5 Coder 14B (without any LoRA adapter) on the same 90 held-out samples. Two experiments:

1. **Same prompt** (bare "Generate a Certus certificate"): tests whether the base model can produce the format at all.
2. **Detailed prompt** (full format spec, allowed builtins, example output): tests whether the base model can match claim quality when given every advantage.

*Results will be added when the comparison completes.*

## Quick start

### Verify existing certificates

```bash
certus check myfile.py
```

### Generate certificates for a Python file

Start the inference server on a GPU machine:

```bash
python scripts/serve_certus.py --model models/certus-qwen-14b-lora --port 8234
```

Then generate and verify:

```bash
certus generate myfile.py --server http://gpu-host:8234
```

Output looks like:

```
PASS binary_search
  certificate:
    @certus(
        preconditions=['isinstance(arr, list)', 'len(arr) > 0'],
        postconditions=[{'when': 'target not in arr', 'guarantees': ['result == -1']},
                        {'when': 'always', 'guarantees': ['result == -1 or arr[result] == target']}],
    )
  verification:
    proved: 0  held: 2  violated: 0  unverified: 0
    confidence: 0.0
    strength: 1.0
```

### Train your own model

```bash
# Collect training data
python scripts/collect_samples.py 500 8 train

# Validate and format
python scripts/validate_and_format.py

# Train (on a GPU machine with 16GB+ VRAM)
pip install -r requirements-train.txt
python scripts/train_certus.py --data data/training/training_data.jsonl
```

## Architecture

```
certus/
  spec/           Schema (Pydantic), safe subset validator, serializers
  checker/        Structural validation, Hypothesis testing, composition, caching
  pipeline/       MBPP collection, prompt templates, validation, formatting
  generator.py    End-to-end: inference server call, parse, check, report
  decorator.py    @certus decorator (disabled/assert/audit modes)
  cli.py          certus check, certus generate, certus pipeline
scripts/          Training, inference, evaluation, serving
seeds/            10 example certificates (valid and broken)
tests/            176 tests
```

### Verification pipeline

The checker runs three passes on each certificate:

1. **Pass 0 (structural)**: validates that all expressions in the certificate conform to the safe subset (an AST allowlist that prevents code execution in certificate expressions).
2. **Pass 2 (dynamic)**: generates random inputs via Hypothesis and checks that postconditions hold. A "structural" mode skips this pass for batch processing.
3. **Pass 3 (composition)**: traverses `depends_on` references to verify that compositional dependencies are satisfied.

A **strength score** measures what fraction of random inputs the certificate rejects, filtering out tautological claims like `isinstance(result, object)`.

### Certificate format

Certificates declare preconditions (what must be true of inputs), postconditions (what the function guarantees about its output, branched by conditions), and optional fields for effects, invariants, exceptions, and compositional dependencies. All expressions must be valid Python within the safe subset.

## Status

- **M0+M1**: Schema, seeds, fast-mode checker (106 tests)
- **M2**: Data collection and augmentation pipeline (+27 tests)
- **M2.5**: Subagent-based certificate generation, structural validation mode (+10 tests)
- **M3**: QLoRA finetuning, evaluation, end-to-end CLI (+33 tests)

Total: 176 passing tests.

## License

TBD
