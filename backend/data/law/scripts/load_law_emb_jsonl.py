import os
import json
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
load_dotenv()

import psycopg
from pgvector.psycopg import register_vector
import numpy as np

# ----------------------------
# Embedding config (HF)
# ----------------------------
EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "nlpai-lab/KURE-v1")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
EMBED_DEVICE = os.environ.get("EMBED_DEVICE")
EMBED_TRUST_REMOTE_CODE = os.environ.get("EMBED_TRUST_REMOTE_CODE", "false").lower() in ("1", "true", "yes", "y")
NORMALIZE_EMBEDDINGS = os.environ.get("NORMALIZE_EMBEDDINGS", "true").lower() in ("1", "true", "yes", "y")

_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer

        kwargs = {"trust_remote_code": EMBED_TRUST_REMOTE_CODE}
        if EMBED_DEVICE:
            kwargs["device"] = EMBED_DEVICE
        _EMBEDDER = SentenceTransformer(EMBED_MODEL_NAME, **kwargs)
    return _EMBEDDER


def conninfo_from_env() -> str:
    return (
        f"host={os.environ.get('PGHOST','localhost')} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ.get('PGDATABASE','ddoksori')} "
        f"user={os.environ.get('PGUSER','postgres')} "
        f"password={os.environ.get('PGPASSWORD','postgres')}"
    )


DDL_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS statute_chunk_vectors (
  unit_id         TEXT NOT NULL,
  embedding_model TEXT NOT NULL,

  law_id          TEXT NOT NULL,
  unit_level      TEXT,
  path            TEXT,

  node_refs       JSONB NOT NULL DEFAULT '[]'::jsonb,
  index_text      TEXT,

  embedding       VECTOR({EMBED_DIM}) NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (unit_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_law_id
  ON statute_chunk_vectors(law_id);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_unit_level
  ON statute_chunk_vectors(unit_level);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_embedding_model
  ON statute_chunk_vectors(embedding_model);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_embedding_hnsw
  ON statute_chunk_vectors
  USING hnsw (embedding vector_cosine_ops);
"""


UPSERT_SQL = """
INSERT INTO statute_chunk_vectors (
  unit_id, embedding_model, law_id, unit_level, path,
  node_refs, index_text, embedding
) VALUES (
  %(unit_id)s, %(embedding_model)s, %(law_id)s, %(unit_level)s, %(path)s,
  %(node_refs)s::jsonb, %(index_text)s, %(embedding)s
)
ON CONFLICT (unit_id, embedding_model) DO UPDATE SET
  law_id=EXCLUDED.law_id,
  unit_level=EXCLUDED.unit_level,
  path=EXCLUDED.path,
  node_refs=EXCLUDED.node_refs,
  index_text=EXCLUDED.index_text,
  embedding_model=EXCLUDED.embedding_model,
  embedding=EXCLUDED.embedding;
"""


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON decode error at {path}:{line_no}: {e}") from e


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    HF embeddings via sentence-transformers.
    - input: list of index_text strings
    - output: list of vector(list[float]) with EMBED_DIM
    """
    if not texts:
        return []
    model = _get_embedder()
    vectors = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def _json_dumps(v: Any) -> str:
    return json.dumps(v if v is not None else [], ensure_ascii=False)


def _validate_vec(vec: List[float], dim: int = EMBED_DIM) -> None:
    if not isinstance(vec, list) or len(vec) != dim:
        raise ValueError(f"embedding dim mismatch: expected {dim}, got {len(vec) if isinstance(vec, list) else type(vec)}")


def load_chunks_jsonl_to_vectors_table(
    jsonl_path: str,
    *,
    batch_size: int = 512,
    use_embedding_field_if_present: bool = True,
) -> None:
    """
    jsonl_path: 청킹 완료 jsonl (unit_id, index_text, node_refs 등 포함)
    - 기본 동작:
      1) row에 embedding 필드가 있으면 그대로 적재
      2) 없으면 embed_texts()로 index_text를 임베딩해서 적재
    """
    conninfo = conninfo_from_env()

    with psycopg.connect(conninfo) as conn:
        register_vector(conn)  # pgvector type adapter 등록

        with conn.cursor() as cur:
            # schema ensure
            cur.execute(DDL_SQL)
            conn.commit()

            buffer_rows: List[Dict[str, Any]] = []
            buffer_texts: List[str] = []
            buffer_meta: List[Dict[str, Any]] = []

            def flush_with_vectors(vectors: List[List[float]]) -> None:
                nonlocal buffer_rows, buffer_texts, buffer_meta

                if len(vectors) != len(buffer_meta):
                    raise RuntimeError("vectors length != buffered rows length")

                rows = []
                for meta, vec in zip(buffer_meta, vectors):
                    _validate_vec(vec)
                    rows.append({
                        **meta,
                        "embedding": np.array(vec, dtype=np.float32),
                    })

                cur.executemany(UPSERT_SQL, rows)
                buffer_rows.clear()
                buffer_texts.clear()
                buffer_meta.clear()

            for row in iter_jsonl(jsonl_path):
                unit_id = row.get("unit_id")
                law_id = row.get("law_id")
                index_text = row.get("index_text")

                if not unit_id or not law_id:
                    continue  # 필수키 없으면 skip (원하면 에러로 바꿔도 됨)
                meta = {
                    "unit_id": unit_id,
                    "law_id": law_id,
                    "embedding_model": row.get("embedding_model") or EMBED_MODEL_NAME,
                    "unit_level": row.get("unit_level"),
                    "path": row.get("path"),
                    "node_refs": _json_dumps(row.get("node_refs") or []),
                    "index_text": index_text,
                }

                # (A) embedding 필드가 이미 있으면 즉시 버퍼에 넣고 flush
                if use_embedding_field_if_present and "embedding" in row and row["embedding"] is not None:
                    vec = row["embedding"]
                    _validate_vec(vec)
                    meta["embedding"] = np.array(vec, dtype=np.float32)
                    buffer_rows.append(meta)

                    if len(buffer_rows) >= batch_size:
                        cur.executemany(UPSERT_SQL, buffer_rows)
                        buffer_rows.clear()
                    continue

                # (B) 없으면 index_text 임베딩해서 넣기
                if not index_text:
                    continue  # 임베딩할 텍스트가 없으면 skip

                buffer_texts.append(index_text)
                buffer_meta.append(meta)

                if len(buffer_texts) >= batch_size:
                    vectors = embed_texts(buffer_texts)
                    flush_with_vectors(vectors)

            # tail flush
            if buffer_rows:
                cur.executemany(UPSERT_SQL, buffer_rows)

            if buffer_texts:
                vectors = embed_texts(buffer_texts)
                flush_with_vectors(vectors)

        conn.commit()


if __name__ == "__main__":
    from pathlib import Path

    need_laws_path = Path(__file__).parent / "../raw/need_laws.json"
    chunks_dir = Path(__file__).parent / "../raw/law_chunks"

    with need_laws_path.open("r", encoding="utf-8") as f:
        need_laws = json.load(f)

    existing_files = []
    missing_files = []

    for code in need_laws.values():
        chunk_file = chunks_dir / f"{code}_chunks.jsonl"
        if chunk_file.exists():
            existing_files.append(chunk_file)
        else:
            missing_files.append(chunk_file)

    if missing_files:
        print(f"⚠️  Skipping {len(missing_files)} missing files:")
        for f in missing_files:
            print(f"  - {f.name}")

    print(f"\n📦 Processing {len(existing_files)} chunk files...\n")

    for chunk_file in existing_files:
        print(f"▶ Processing: {chunk_file.name}")
        load_chunks_jsonl_to_vectors_table(str(chunk_file), batch_size=512)
        print(f"✓ Done: {chunk_file.name}\n")
