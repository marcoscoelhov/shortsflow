# EVAL: local-vision-model-bakeoff

## Question

Which local vision model can reject known misleading ShortsFlow images and
accept a coherent control image on this 2-core, 8 GiB machine without a paid
API?

## Cases defined before execution

1. `uranus_wrong` — expected `reject`. The image shows two ringed planets and
   does not make Uranus's near-horizontal rotation axis legible.
2. `venus_wrong` — expected `reject`. The main planet resembles Jupiter and the
   image does not show the requested Mercury-versus-Venus comparison.
3. `fiction_control` — expected `accept`. The image visibly contains an
   underground library, a central stone pedestal, a metal key and a glowing
   open book. Missing rising sand is a defect, but not enough to reject this
   positive semantic-control case.

## Candidate policy

- Qwen is excluded because the owner reports that it already failed in prior
  real use.
- Evaluate already-downloaded Gemma 4 E2B and MiniCPM-V 4.6 first.
- Download SmolVLM2 only if neither existing candidate clears the gate.

## Success criteria

- 3/3 classification agreement with the human labels on the first attempt.
- A strict JSON object is returned for every case.
- No single case exceeds 120 seconds after the model is loaded.
- The server stays within available RAM plus existing swap and does not crash.

## Initial screening result — 2026-07-31

| Candidate | Result | Operational evidence |
| --- | --- | --- |
| Gemma 4 E2B Q4 | **FAIL (2/3)** | Rejected the bad Uranus image and accepted the control, but incorrectly accepted the Jupiter-like Venus image. Valid JSON; 35.42–38.71 seconds per case. |
| MiniCPM-V 4.6 Q4 | **FAIL** | Produced a malformed response with extra JSON data, violating the existing strict response contract. |
| SmolVLM2 2.2B Q4 | **FAIL** | Produced truncated/malformed JSON in two runs, including after increasing the output allowance. |

No candidate clears the screening gate. Qwen remains excluded based on the
owner's prior production experience. Do not install any of these models as an
automatic publication authority.

## Qwen rerun requested by the owner

Model already present on disk: `Qwen3-VL-2B-Instruct Q4_K_M`, initially with
the F16 visual projector.

### Baseline rerun

- Semantic decisions: **3/3 correct**.
- Uranus: rejected two Saturn-like ringed planets and the illegible tilt.
- Venus: identified the main planet as Jupiter rather than Mercury or Venus.
- Fiction control: accepted the library, pedestal, key and glowing book.
- Latency: 67.17–79.00 seconds per image.
- Transport contract: 0/3 strict JSON because the model added a duplicate
  object, a trailing quote or a Markdown fence.

### Optimized rerun

Configuration: 512 visual tokens, 2,048-token context, Flash Attention,
disabled prompt cache, schema-shaped response, two CPU threads.

- Semantic decisions: **3/3 correct**.
- Latency with the existing generic AVX2 build: 30.50–35.52 seconds per image,
  32.46 seconds on average.
- Latency with a disposable native CPU build: 26.93–28.35 seconds per image,
  27.76 seconds on average.
- Native compilation improved the optimized average by about **14.5%**.
- The optimized native run was about **61% faster** than the baseline average.
- Qwen still sometimes wraps or duplicates valid JSON. Using
  `json.JSONDecoder().raw_decode()` from the first `{` recovered all three
  decisions deterministically without another model call.

The earlier exclusion is therefore superseded: Qwen is the only tested model
that passed all three semantic cases. It is a **provisional candidate**, not a
publication authority, until it passes the 20-image release eval.

## CPU diagnosis and model shortlist

The host exposes two virtual AMD EPYC cores, one NUMA node and 8 GiB RAM. During
vision inference both cores are saturated, I/O wait is negligible and there is
no active swapping pressure; compute is the bottleneck. The existing build is
Release + OpenMP but generic AVX2, while the CPU exposes AVX-512, VNNI and BF16.

Other llama.cpp-compatible candidates that fit this host:

1. [InternVL3-2B-Instruct GGUF](https://huggingface.co/ggml-org/InternVL3-2B-Instruct-GGUF)
   — best fallback to test if Qwen fails the expanded local eval. Its upstream
   family reports stronger real-world and hallucination results than earlier
   InternVL generations.
2. [InternVL3-1B-Instruct GGUF](https://huggingface.co/ggml-org/InternVL3-1B-Instruct-GGUF)
   — faster/lighter, but less attractive for subtle planet identification.
3. [Moondream2 GGUF](https://huggingface.co/ggml-org/moondream2-20250414-GGUF)
   — CPU-oriented edge option, but older and less suitable for complex visual
   contradictions than Qwen or InternVL3-2B.

Models at 4B or above may fit when quantized, but are not sensible defaults on
two cores. InternVL3-2B is the only additional download justified before trying
larger hardware or a paid API.

## Release rule

This is a screening eval, not sufficient evidence for production. Any future
winner must pass at least 20 labeled images with recall prioritized over
precision for misleading scientific visuals.

## Decision implication

For the zero-recurring-cost pilot, keep the existing **Astronomia Visualmente
Ancorada** policy: official/licensed assets or programmatic compositions remain
the factual visual evidence. Qwen can become an additional contradiction gate
after the expanded eval, but generative images must not become scientific proof
solely because a small local VLM accepted them.

Operational clarification after the 2026-07-31 review: even after the expanded
eval, automatic authority for generic cosmos content also requires provenance
from the exact approved `local_openai` model with no fallback on every critical
scene. The current fresh-attempt path does not yet prove that invariant, so keep
`SHORTSFLOW_LOCAL_VISION_RELEASE_APPROVED=false`. The `survival_decisions`
pilot separately requires human review and cannot use this release as an
automatic-publication waiver.
