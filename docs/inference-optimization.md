# Model inference optimization plan

Status: **planned for Milestone 2, not implemented or benchmarked in Milestone 1**. No model weights or additional runtime dependencies are installed by this documentation change.

## What each component does

| Component | Role in this project | Decision |
| --- | --- | --- |
| PyTorch / Sentence Transformers | Reference embedding and cross-encoder inference | Establish the correctness and retrieval-quality baseline first. |
| ONNX | Portable exported model graph format | Export only a pinned, approved model with its tokenizer and preprocessing contract. It is not a runtime or vector database. |
| ONNX Runtime | Executes ONNX models through hardware execution providers | First optional runtime to benchmark; start with CPU, then evaluate an available supported accelerator. |
| OpenVINO | Inference optimization/runtime for supported Intel hardware | Optional Intel CPU/GPU/NPU deployment path; verify exact model, device and operator support. |
| ONNX Runtime OpenVINO execution provider | Runs supported ONNX operations through OpenVINO | Alternative to a direct OpenVINO backend; choose one integration route per deployment rather than stacking redundant wrappers. |
| CUDA / TensorRT execution providers | Potential NVIDIA acceleration through ONNX Runtime | Evaluate only if the target deployment has suitable NVIDIA hardware and a measured need. |

Sentence Transformers documents ONNX and OpenVINO backends for embedding models and cross-encoders. That does **not** establish compatibility for every BGE checkpoint, quantization mode, model architecture, operator or device. Prove the chosen combination before advertising support.

## Where optimization belongs

1. **Document embeddings:** batch approved chunks before writing vectors to Qdrant.
2. **Query embeddings:** produce vectors with the same compatible embedding contract as indexed documents.
3. **BGE reranking:** score a bounded set of candidates after BM25/dense retrieval and Reciprocal Rank Fusion.

These runtimes do not replace Qdrant/HNSW, OpenSearch/BM25, RRF, PostgreSQL, LangGraph orchestration or approval controls. They optimize local model inference. They cannot accelerate a remotely hosted Azure OpenAI model by changing a local runtime.

## Implementation sequence

1. Select licensed, pinned BGE embedding and reranker checkpoints; establish PyTorch outputs and held-out retrieval metrics. Record CPU/GPU/NPU, memory, OS and dependency versions.
2. Add typed embedding/reranking service interfaces and optional dependency groups for the selected backend. Keep the API/data-foundation install lightweight. Blocking inference belongs in a bounded worker/executor, not the async HTTP event loop.
3. Export models in an explicit offline preparation command. Persist the model graph, tokenizer, pooling/normalization configuration, output dimensions, revision, precision and artifact hashes. Reuse approved artifacts instead of exporting on every request.
4. Test ONNX Runtime CPU and available accelerator providers. Test OpenVINO only on compatible hardware; record the provider/device actually used, including any CPU fallback.
5. Measure FP32 first. Evaluate supported FP16/INT8 variants separately; any calibration data must be licensed, access-controlled and separate from the held-out evaluation set.
6. Publish a benchmark report and promote only a backend that meets agreed quality and operational thresholds. Select thresholds before comparing final candidates. Do not promise a fixed speedup without measurements.

## Benchmark and acceptance gates

Use identical model revisions, tokenization, truncation, pooling, normalization, candidate sets and evaluation queries. Fix batch sizes and input-length distributions; report cold start separately from warmed runs.

- Numerical checks: output shape, finite values, normalization, embedding agreement and reranker-score/ranking differences against the reference. Small floating-point differences require tolerances chosen for the model.
- Retrieval quality: nDCG@10, MRR@10 and Recall@k on held-out judgments, including long inputs and error-code-heavy queries. Embedding cosine agreement alone does not establish retrieval equivalence.
- Performance: p50/p95/p99 latency, throughput, memory, model size, export/startup time and CPU/GPU utilization. Report hardware, concurrency and input lengths alongside results.
- Reliability: empty/oversized input, bounded batches, cancellation, inference timeout, unavailable provider, invalid/corrupted artifacts and out-of-memory behavior.
- Deployment: model licensing, reproducible dependencies, artifact hashes, explicit device selection, rollback and observability must pass before promotion.

## Guardrails and fallback

- Model/provider selection comes from trusted configuration, never incident text, retrieved documents or agent output.
- Pin and allowlist artifacts; verify checksums and keep weights out of Git. Do not enable unreviewed remote model code. Treat exported graphs as untrusted compute artifacts and load them in a resource-limited worker.
- Cap text length, candidate count, batch size, queue depth, concurrency and wall time. Do not log raw incident/document text or vectors.
- Record model revision, runtime, provider, precision and timing. Alert on unexpected CPU fallback instead of silently describing the system as accelerated.
- If a provider is unavailable, either fail readiness or use an explicitly permitted and evaluated fallback. Never silently switch the embedding model, dimensions, tokenizer or normalization. Those changes require a versioned index/re-embedding and rollback plan.
- If reranking fails, a policy may return the already-authorized fused candidate ranking, clearly marked as not reranked. It must not bypass evidence, ACL or approval checks.

## Recommended order

Start with **PyTorch baseline -> ONNX Runtime benchmark -> optional OpenVINO benchmark on Intel hardware**. Choose from measured results. Ray/distributed inference and additional vector databases remain separate scale decisions.

## Primary references

- [Sentence Transformers embedding inference backends](https://www.sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [Sentence Transformers cross-encoder inference backends](https://www.sbert.net/docs/cross_encoder/usage/efficiency.html)
- [ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [OpenVINO execution provider](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html)
