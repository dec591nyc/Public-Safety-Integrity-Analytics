# AI Summary Alternatives

## Decision

Use a staged provider architecture:

1. `extractive` is the default during local development. It uses indexed text snippets, never sends data outside the machine, and always returns evidence text.
2. `ollama` is the preferred optional local generative provider after hardware and model quality testing.
3. `llama.cpp` is the lower-level deployment option when tighter runtime control or an OpenAI-compatible local endpoint is needed.
4. `transformers_js` is experimental only. It is useful for lightweight classification, but browser-side Chinese legal summarization would impose a large model download and weak performance on the current CPU-only machine.
5. `openai` is deferred until production deployment. No API key is required or stored now.

## Comparison

| Provider | Account/API key | Data leaves device | Current fit | Main limitation |
| --- | --- | --- | --- | --- |
| Extractive rules | No | No | Default now | Cannot infer facts that are absent from the indexed excerpt |
| Ollama | No after model download | No | Best local generative option | Not installed; CPU inference may be slow |
| llama.cpp server | No after model download | No | Advanced deployment option | More setup and model management |
| Transformers.js | No | No after model caching | Lightweight classification experiment | Large browser downloads and WebGPU variability |
| OpenAI API | Yes, later | Yes | Production option later | Credential, cost, privacy review, and network dependency |

## Current Machine Constraint

- No NVIDIA GPU was detected.
- Ollama is not installed.
- Eight logical CPU processors were detected.

This makes browser text generation and medium/large local language models unsuitable as the default interactive path. A small local model can still be evaluated as an offline batch job.

## Traceability Requirements

Every summary record should store:

- `summary_text`
- `summary_provider`
- `summary_model`
- `summary_version`
- `source_text_hash`
- `evidence_snippets`
- `generated_at`
- `confidence`
- `needs_manual_review`

Summaries are navigation aids, not legal findings. Public claims require source review.

## Official Sources

- Ollama API: https://docs.ollama.com/api/introduction
- Ollama repository: https://github.com/ollama/ollama
- llama.cpp server: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- Transformers.js: https://huggingface.co/docs/transformers.js
- ONNX Runtime Web: https://onnxruntime.ai/docs/tutorials/web/

