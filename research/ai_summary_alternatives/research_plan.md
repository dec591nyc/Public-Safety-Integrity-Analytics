# AI summary alternatives research plan

## Main question
How can the judicial dashboard provide useful, traceable summaries without using the OpenAI API during local development?

## Subtopics
1. Deterministic extractive summarization for court documents, including evidence snippets and limitations.
2. Local server inference through Ollama or llama.cpp, including installation, resource, privacy, and automation tradeoffs.
3. Browser-side inference through Transformers.js/WebGPU, including model download size, Chinese support, caching, and user experience.

## Synthesis
Choose a staged architecture for this repository. OpenAI remains a deferred production provider. The current implementation must disclose its summary method and preserve source evidence.
