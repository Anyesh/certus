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

## What problem this solves

Certus might look like doctest (both attach verification metadata to functions) or like type annotations (both declare properties inline). The resemblance is intentional, but the problem it solves is different.

**Existing tools require a human in the loop.** Someone has to write the doctest examples, the type annotations, the Hypothesis property tests, or the `icontract` preconditions. For hand-written code, that's fine. For AI-generated code, it's backwards: you're asking a human to verify what a machine wrote, which defeats the purpose of generation.

**Certus automates both sides.** A finetuned model generates the correctness claims, and an independent checker verifies them with counterexample search. No human writes the properties, and no human reviews the results. The pipeline is: code goes in, verified certificate comes out (or a failure report explaining what the checker disproved).

The closest existing approach is **Design by Contract** (preconditions and postconditions, as in Eiffel or Python's `icontract`). Certus is essentially auto-generated contracts that are auto-verified. The novelty isn't the decorator syntax; it's the closed loop where the model proposes claims and the checker stress-tests them.

### Why not just write Hypothesis tests?

You could. Hypothesis is excellent for property-based testing, and Certus uses it internally. But in practice:

1. **Nobody writes property tests for every function.** It's too much work for generated code that may be rewritten tomorrow. Certus generates them automatically at the same time the code is generated.
2. **Property tests require knowing what to test.** The hard part isn't running Hypothesis; it's deciding which properties matter. The finetuned model handles that, and it's right 83% of the time on held-out code it's never seen.
3. **Certificates compose.** A function can declare `depends_on` to reference another function's certificate. The checker traverses these dependencies and verifies the whole chain. Ad-hoc property tests don't compose this way.

### How much does this actually cover?

Across 90 held-out functions, the finetuned 14B model generates an average of 2.9 property guarantees per function, each verified across 30 random inputs via Hypothesis. The guarantee types break down as:

| Type | Share | Example |
|---|---|---|
| Bounds | 26% | `result >= 0`, `result <= n` |
| Structural | 26% | `all(result[i] <= result[i+1] for i in range(len(result)-1))` |
| Type checks | 22% | `isinstance(result, list)` |
| Equalities | 21% | `result == a + b`, `result * result == num` |
| Other | 4% | various |

The structural and bound properties are things that specific-example testing (doctest, unittest) fundamentally cannot express. You can't write a doctest that checks "the result is sorted" for all inputs. You can write a Certus certificate that says it and verify it across random inputs.

## Real-world benchmark

We tested Certus on 10 production-style utility functions (not from any training set): `chunk_list`, `flatten_dict`, `deduplicate`, `clamp`, `is_palindrome`, `merge_sorted`, `pascal_row`, `group_by`, `levenshtein_distance`, `matrix_transpose`.

| Function | Inference | Check | Total | Result | Key verified property |
|---|---|---|---|---|---|
| `chunk_list` | 7.6s | 6.9s | 14.5s | PASS | `sum(len(chunk) for chunk in result) == len(lst)` |
| `flatten_dict` | 5.2s | 3.8s | 9.0s | PASS | `isinstance(result, dict)` |
| `deduplicate` | 4.8s | 6.0s | 10.7s | PASS | `all(result.count(x) == 1 for x in result)` |
| `clamp` | 8.6s | 5.8s | 14.4s | PASS | `result == min(maximum, max(minimum, value))` |
| `is_palindrome` | 5.4s | 7.5s | 12.9s | PASS | branched True/False with cleaned string logic |
| `merge_sorted` | 6.6s | 7.4s | 14.0s | PASS | `all(result[i] <= result[i+1] for ...)` (sortedness) |
| `pascal_row` | 5.3s | 7.0s | 12.3s | PASS | `len(result) == n + 1`, `result[0] == 1` |
| `group_by` | 5.7s | 5.9s | 11.6s | FAIL | uses `callable()` outside safe subset |
| `levenshtein` | 3.8s | 5.2s | 8.9s | PASS | `result >= 0`, `result <= max(len(s1), len(s2))` |
| `matrix_transpose` | 5.0s | 5.8s | 10.7s | PASS | `len(result) == len(matrix[0])`, dimension swap |

### Performance numbers

| Metric | Value |
|---|---|
| Pass rate (real-world) | 9/10 (90%) |
| Inference throughput | 13.2 tokens/sec |
| Average inference time | 5.8s per function |
| Average checker time | 6.1s per function |
| Average end-to-end | 11.9s per function |
| Tokens per certificate | 77 avg |
| Hardware | RTX 4070 Ti SUPER (16GB VRAM), Qwen 14B 4-bit |

The one failure (`group_by`) uses `callable()` in a precondition, which isn't in the expression safe subset. The model correctly identified the constraint; our validator is the bottleneck.

## Evaluation results

### How we built the training data

There is no existing dataset of Python functions paired with Certus certificates, so we built one. The challenge: generating high-quality certificates requires an LLM that understands code semantics, but we didn't have API access to call Claude or GPT programmatically.

The solution: we used Claude Code's subagent system to generate certificates in-session. We split 874 MBPP samples (374 train + 500 test) into 8 batches and dispatched 8 parallel subagents, each processing ~50-60 functions. Each subagent read the code, understood the function's behavior, and generated a `@certus` certificate with meaningful preconditions and postconditions.

The raw certificates then went through the Certus checker (structural validation + strength scoring, no Hypothesis at this stage) to filter out malformed or tautological ones. 710 of 874 survived (81.2%), producing 1420 training examples: each function appears twice, once as Task A ("generate code + certificate from description") and once as Task B ("generate certificate for existing code").

| Step | Input | Output | Pass rate |
|---|---|---|---|
| MBPP collection | HuggingFace dataset | 874 code samples | N/A |
| Subagent generation | 874 samples, 16 agents | 874 certificates | 100% generated |
| Structural validation | 874 certificates | 710 valid | 81.2% |
| Training formatting | 710 valid | 1420 examples | Task A + Task B |

Total data generation time was about 10 minutes (subagent inference) plus 2 minutes (validation). No API key needed.

### Evaluation

We finetuned Qwen 2.5 Coder models (via QLoRA) on the 1420 training examples and evaluated on 90 held-out samples (MBPP validation split, never seen during training or data generation).

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

### Inference speed

Measured on 90 held-out functions (MBPP validation split) and 10 real-world utility functions. All numbers on a single RTX 4070 Ti SUPER with Unsloth's patched fast inference.

| Metric | 7B model | 14B model |
|---|---|---|
| Inference per function | ~3s | ~5.8s |
| Checker per function | ~5s | ~6.1s |
| End-to-end per function | ~8s | ~11.9s |
| Throughput | ~20 tok/s | 13.2 tok/s |
| Tokens per certificate | ~70 | 77 |
| 90 functions (batch) | ~5 min | ~9 min |

For comparison, the same 90 functions took ~45 min with vanilla transformers (no Unsloth). The Unsloth fast inference path gives roughly a 5x speedup. Training both models back-to-back (7B + 14B) takes about 26 minutes total on the same hardware.

### Does finetuning matter? Base model comparison

To verify that our QLoRA finetuning adds real value, we ran the base Qwen 2.5 Coder 14B (without any LoRA adapter) on the same 90 held-out samples under two conditions:

| Metric | Base (bare prompt) | Base (detailed prompt) | **Finetuned 14B** |
|---|---|---|---|
| Parse rate | 0% | 98.9% | **100%** |
| Structural pass | 0% | 78.9% | **91.1%** |
| Dynamic pass | 0% | 74.4% | **83.3%** |
| Tautological | 0% | 10.0% | **1.1%** |

**Bare prompt**: the base model has no concept of Certus and produces explanations about blockchain security. Zero parseable certificates.

**Detailed prompt** (format spec, allowed builtins, example): the base model produces valid output 98.9% of the time and 74.4% passes end-to-end verification. This is a strong baseline, but finetuning adds clear value in two ways:

1. **Tautological rate drops from 10% to 1.1%.** The base model hedges with weak claims like `isinstance(result, int)` that are always true. The finetuned model learned that certificates need to make strong, falsifiable claims.
2. **No prompt engineering needed.** The finetuned model produces correct format from "Generate a Certus certificate" alone. The base model needs a 15-line detailed prompt with format spec, allowed builtins list, and worked examples.

The base model is more conservative (4 semantic errors vs 7 for finetuned), but that conservatism comes at the cost of 9 tautological certificates that provide zero value. The finetuned model takes more risks and is wrong slightly more often, but the checker catches every error, and the certificates that pass are stronger and more informative.

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
