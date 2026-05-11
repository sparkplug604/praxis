"""Shared helpers for the Praxis semantic vector index."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import urllib.request
from array import array
from pathlib import Path
from typing import Any, Iterable

from praxis.paths import default_root


DEFAULT_ROOT = default_root()
DEFAULT_VECTOR_DB = DEFAULT_ROOT / "vectors" / "semantic_index.sqlite"
DEFAULT_KG_DB = DEFAULT_ROOT / "kg" / "skill_graph.sqlite"
DEFAULT_LOCAL_MODEL = "local-hash-bow-384"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
USER_AGENT = "PraxisVectorRAG/0.1 (+local semantic index)"
OPENAI_EMBEDDING_PRICES_PER_1M = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(text: str, *, max_len: int = 96) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"https?://", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    if not lowered:
        lowered = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return lowered[:max_len].strip("-") or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect(db_path: Path = DEFAULT_VECTOR_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS semantic_documents (
          id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL DEFAULT '',
          capture_id TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL,
          path TEXT NOT NULL DEFAULT '',
          url TEXT NOT NULL DEFAULT '',
          source_type TEXT NOT NULL DEFAULT 'local',
          content_hash TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'active',
          indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS semantic_chunks (
          id TEXT PRIMARY KEY,
          document_id TEXT NOT NULL REFERENCES semantic_documents(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL DEFAULT '',
          capture_id TEXT NOT NULL DEFAULT '',
          chunk_index INTEGER NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          section TEXT NOT NULL DEFAULT '',
          text TEXT NOT NULL,
          text_hash TEXT NOT NULL,
          token_estimate INTEGER NOT NULL DEFAULT 0,
          source_type TEXT NOT NULL DEFAULT 'local',
          confidence TEXT NOT NULL DEFAULT 'medium',
          graph_node_ids_json TEXT NOT NULL DEFAULT '[]',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(document_id, chunk_index)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS semantic_chunks_fts
        USING fts5(chunk_id UNINDEXED, title, section, text);

        CREATE TABLE IF NOT EXISTS embedding_models (
          id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          distance_metric TEXT NOT NULL DEFAULT 'cosine',
          config_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chunk_embeddings (
          chunk_id TEXT NOT NULL REFERENCES semantic_chunks(id) ON DELETE CASCADE,
          model_id TEXT NOT NULL REFERENCES embedding_models(id) ON DELETE CASCADE,
          vector BLOB NOT NULL,
          vector_hash TEXT NOT NULL,
          norm REAL NOT NULL,
          dimensions INTEGER NOT NULL,
          embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          status TEXT NOT NULL DEFAULT 'active',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY(chunk_id, model_id)
        );

        CREATE TABLE IF NOT EXISTS retrieval_logs (
          id TEXT PRIMARY KEY,
          query TEXT NOT NULL,
          mode TEXT NOT NULL,
          model_id TEXT NOT NULL DEFAULT '',
          result_count INTEGER NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_semantic_documents_source ON semantic_documents(source_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_documents_hash ON semantic_documents(content_hash);
        CREATE INDEX IF NOT EXISTS idx_semantic_chunks_document ON semantic_chunks(document_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_chunks_source ON semantic_chunks(source_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_chunks_hash ON semantic_chunks(text_hash);
        CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model_id);
        """
    )


def estimate_tokens(text: str) -> int:
    # Conservative local estimate. Good enough for chunk sizing without tokenizer deps.
    return max(1, math.ceil(len(text) / 4))


def normalize_space(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_+\-./]{1,}", text.lower())


def chunk_text(text: str, *, target_chars: int = 1800, overlap_chars: int = 250) -> list[dict[str, Any]]:
    text = normalize_space(text)
    if not text:
        return []

    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_section = ""

    def flush() -> None:
        nonlocal current
        if not current:
            return
        chunk = normalize_space("\n\n".join(current))
        if chunk:
            chunks.append({"section": current_section, "text": chunk})
        if overlap_chars > 0 and chunk:
            overlap = chunk[-overlap_chars:]
            current = [overlap]
        else:
            current = []

    for block in blocks:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", block)
        if heading_match:
            current_section = heading_match.group(2).strip()[:240]
        candidate_len = len("\n\n".join(current + [block]))
        if current and candidate_len > target_chars:
            flush()
        current.append(block)
        if len("\n\n".join(current)) >= target_chars:
            flush()

    if current:
        # Avoid creating an overlap-only tail.
        tail = normalize_space("\n\n".join(current))
        if tail and (not chunks or tail != chunks[-1]["text"]):
            chunks.append({"section": current_section, "text": tail})

    return chunks


def vector_norm(vector: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def normalize_vector(vector: list[float]) -> list[float]:
    norm = vector_norm(vector)
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def pack_vector(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack_vector(blob: bytes) -> list[float]:
    values = array("f")
    values.frombytes(blob)
    return list(values)


def vector_hash(vector: list[float]) -> str:
    return hashlib.sha256(pack_vector(vector)).hexdigest()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = vector_norm(left)
    right_norm = vector_norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    return dot / (left_norm * right_norm)


def local_hash_embedding(text: str, *, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    features: list[str] = []
    features.extend(tokens)
    features.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:]))
    features.extend(f"char:{text.lower()[idx:idx + 4]}" for idx in range(0, max(0, min(len(text), 8000) - 3), 2))

    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    return normalize_vector(vector)


def openai_embeddings(texts: list[str], *, model: str, dimensions: int | None) -> list[list[float]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; use --provider local-hash or set the key.")
    payload: dict[str, Any] = {
        "model": model,
        "input": texts,
        "encoding_format": "float",
    }
    if dimensions:
        payload["dimensions"] = dimensions
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    data = sorted(body["data"], key=lambda item: item["index"])
    return [normalize_vector([float(value) for value in item["embedding"]]) for item in data]


def embed_texts(texts: list[str], *, provider: str, model: str, dimensions: int | None = None) -> list[list[float]]:
    if provider == "local-hash":
        dims = dimensions or 384
        return [local_hash_embedding(text, dimensions=dims) for text in texts]
    if provider == "openai":
        return openai_embeddings(texts, model=model or DEFAULT_OPENAI_MODEL, dimensions=dimensions)
    raise ValueError(f"Unsupported embedding provider: {provider}")


def model_id(provider: str, model: str, dimensions: int) -> str:
    return f"embed:{slug(provider)}:{slug(model)}:{dimensions}"


def upsert_embedding_model(
    connection: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    dimensions: int,
    distance_metric: str = "cosine",
    config: dict[str, Any] | None = None,
) -> str:
    identifier = model_id(provider, model, dimensions)
    connection.execute(
        """
        INSERT INTO embedding_models(id, provider, model, dimensions, distance_metric, config_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          provider=excluded.provider,
          model=excluded.model,
          dimensions=excluded.dimensions,
          distance_metric=excluded.distance_metric,
          config_json=excluded.config_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (identifier, provider, model, dimensions, distance_metric, json.dumps(config or {}, sort_keys=True)),
    )
    return identifier


def fts_query(query: str) -> str:
    terms = tokenize(query)
    if not terms:
        return '""'
    return " OR ".join(f'"{term}"' for term in terms[:12])


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_env_file(path: Path) -> bool:
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def estimate_embedding_cost(token_estimate: int, model: str) -> float:
    return token_estimate * OPENAI_EMBEDDING_PRICES_PER_1M.get(model, 0.0) / 1_000_000
