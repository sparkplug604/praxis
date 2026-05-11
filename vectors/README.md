# Semantic Vector Index

This folder contains the local semantic retrieval layer for Praxis.

The governing shape is:

```text
source capture -> chunk -> embed -> vector/keyword retrieval
source capture -> proposal -> review -> graph update
```

Embeddings are allowed to update automatically because they are retrieval indexes, not truth claims. Durable SkillGraph claims still require proposal, review, and apply.

## Commands

Chunk local sources:

```bash
python3.12 "../scripts/chunk_sources.py" --reset
```

The default chunker can include an optional runtime/source corpus from:

```text
../sources/runtime_corpus.example.json
```

To rebuild without runtime source files:

```bash
python3.12 "../scripts/chunk_sources.py" --reset --no-runtimes
```

Embed chunks with the dependency-free local fallback:

```bash
python3.12 "../scripts/index_vectors.py" --provider local-hash
```

Use OpenAI embeddings when `OPENAI_API_KEY` is available:

```bash
cp .env.example .env
# edit .env locally, then:
python3.12 "../scripts/check_embedding_setup.py" --env-file .env
python3.12 "../scripts/check_embedding_setup.py" --env-file .env --live
python3.12 "../scripts/index_vectors.py" --provider openai --model text-embedding-3-small --env-file .env
```

Estimate cost without embedding:

```bash
python3.12 "../scripts/index_vectors.py" --provider openai --model text-embedding-3-small --estimate-only --env-file .env
```

Search:

```bash
python3.12 "../scripts/semantic_search.py" "agent skill memory retrieval" --show-text
python3.12 "../scripts/hybrid_search.py" "knowledge to skill loop" --show-text
python3.12 "../scripts/hybrid_search.py" "knowledge to skill loop" --provider openai --model text-embedding-3-small --env-file .env --show-text
```

Run smoke evals:

```bash
python3.12 "../scripts/eval_retrieval.py"
```

## Notes

The default `local-hash` provider is a zero-dependency lexical vector fallback. It is useful for smoke tests and offline retrieval, but it is not a frontier semantic embedding model. For real semantic retrieval, use OpenAI embeddings or install a local embedding model backend.
