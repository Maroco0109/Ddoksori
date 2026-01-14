import os
import json
from typing import Any, Dict, Iterable, List, Optional
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import psycopg

load_dotenv()


# =========================================================
# Connection
# =========================================================
def conninfo_from_env() -> str:
    """
    환경변수 기반 psycopg conninfo 생성
    - PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
    """
    return (
        f"host={os.environ.get('PGHOST','localhost')} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ.get('PGDATABASE','ddoksori')} "
        f"user={os.environ.get('PGUSER','postgres')} "
        f"password={os.environ.get('PGPASSWORD','postgres')}"
    )


# =========================================================
# IMPORTANT: 기존에 이미 생성된 테이블을 그대로 사용
# - laws, law_units만 적재
# - law_version, law_citation_map에는 적재하지 않음
# - 여기서는 CREATE TABLE / DROP TABLE 같은 스키마 변경 DDL을 수행하지 않음
# =========================================================


# =========================================================
# UPSERT SQL (target tables: laws, law_units)
# =========================================================
UPSERT_LAW_SQL = """
INSERT INTO laws (
  law_id, law_name, law_type, ministry,
  promulgation_date, enforcement_date, revision_type,
  domain
) VALUES (
  %(law_id)s, %(law_name)s, %(law_type)s, %(ministry)s,
  %(promulgation_date)s, %(enforcement_date)s, %(revision_type)s,
  %(domain)s
)
ON CONFLICT (law_id) DO UPDATE SET
  law_name=EXCLUDED.law_name,
  law_type=COALESCE(EXCLUDED.law_type, laws.law_type),
  ministry=COALESCE(EXCLUDED.ministry, laws.ministry),
  promulgation_date=COALESCE(EXCLUDED.promulgation_date, laws.promulgation_date),
  enforcement_date=COALESCE(EXCLUDED.enforcement_date, laws.enforcement_date),
  revision_type=COALESCE(EXCLUDED.revision_type, laws.revision_type),
  domain=COALESCE(EXCLUDED.domain, laws.domain),
  updated_at=NOW();
"""


UPSERT_LAW_UNITS_SQL = """
INSERT INTO law_units (
  doc_id, law_id, parent_id,
  level, is_indexable,

  article_no, article_title, paragraph_no, item_no, subitem_no,
  path, section_path, chapter_no, chapter_name, section_no, section_name,

  text, amendment_note,
  search_stage,

  ref_citations_internal, ref_citations_external, mentioned_laws
) VALUES (
  %(doc_id)s, %(law_id)s, %(parent_id)s,
  %(level)s, %(is_indexable)s,

  %(article_no)s, %(article_title)s, %(paragraph_no)s, %(item_no)s, %(subitem_no)s,
  %(path)s, %(section_path)s::jsonb, %(chapter_no)s, %(chapter_name)s, %(section_no)s, %(section_name)s,

  %(text)s, %(amendment_note)s,
  %(search_stage)s,

  %(ref_citations_internal)s::jsonb, %(ref_citations_external)s::jsonb, %(mentioned_laws)s::jsonb
)
ON CONFLICT (doc_id) DO UPDATE SET
  law_id=EXCLUDED.law_id,
  parent_id=EXCLUDED.parent_id,
  level=EXCLUDED.level,
  is_indexable=EXCLUDED.is_indexable,

  article_no=EXCLUDED.article_no,
  article_title=EXCLUDED.article_title,
  paragraph_no=EXCLUDED.paragraph_no,
  item_no=EXCLUDED.item_no,
  subitem_no=EXCLUDED.subitem_no,

  path=EXCLUDED.path,
  section_path=EXCLUDED.section_path,
  chapter_no=EXCLUDED.chapter_no,
  chapter_name=EXCLUDED.chapter_name,
  section_no=EXCLUDED.section_no,
  section_name=EXCLUDED.section_name,

  text=EXCLUDED.text,
  amendment_note=EXCLUDED.amendment_note,
  search_stage=EXCLUDED.search_stage,

  ref_citations_internal=EXCLUDED.ref_citations_internal,
  ref_citations_external=EXCLUDED.ref_citations_external,
  mentioned_laws=EXCLUDED.mentioned_laws,

  updated_at=NOW();
"""


# =========================================================
# Helpers
# =========================================================
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


def _json_dumps(v: Any) -> str:
    """
    JSONB 컬럼에 넣기 위한 안전한 stringify.
    - None이면 []
    - dict/list 모두 json 문자열로 변환
    """
    if v is None:
        v = []
    return json.dumps(v, ensure_ascii=False)


def parse_yyyymmdd_to_date(s: Optional[str]) -> Optional[date]:
    """
    JSONL의 날짜 문자열이 '20260102' 형태로 들어오는 경우를 DATE로 변환.
    - None/빈값이면 None
    - 길이/형식 이상하면 ValueError
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"Invalid YYYYMMDD date string: {s}")
    y = int(s[0:4])
    m = int(s[4:6])
    d = int(s[6:8])
    return date(y, m, d)


def _to_text_or_none(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def extract_law_row(row: Dict[str, Any]) -> Dict[str, Any]:
    eff = row.get("effective") or {}
    return {
        "law_id": (row.get("law_id") or "").strip(),
        "law_name": (row.get("law_name") or "").strip(),
        "law_type": row.get("law_type"),
        "ministry": row.get("ministry"),
        "promulgation_date": parse_yyyymmdd_to_date(eff.get("promulgation_date")),
        "enforcement_date": parse_yyyymmdd_to_date(eff.get("enforcement_date")),
        "revision_type": eff.get("revision_type"),
        "domain": row.get("domain") or "statute",
    }


def extract_node_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    law_units 스키마(현재 DB)에 맞춰 row를 정규화.
    """
    section_path = row.get("section_path")
    if section_path is None:
        section_path = []  # DB에서 NOT NULL로 바꾸든 아니든, 일단 항상 []로 넣는 게 안전

    return {
        "doc_id": row.get("doc_id"),
        "law_id": row.get("law_id"),
        "parent_id": row.get("parent_id"),

        "level": row.get("level") or "",
        "is_indexable": bool(row.get("is_indexable", True)),

        "article_no": row.get("article_no"),
        "article_title": row.get("article_title"),
        "paragraph_no": _to_text_or_none(row.get("paragraph_no")),
        "item_no": _to_text_or_none(row.get("item_no")),
        "subitem_no": _to_text_or_none(row.get("subitem_no")),

        "path": row.get("path"),

        # 섹션/편장절
        "section_path": _json_dumps(section_path),
        "chapter_no": row.get("chapter_no"),
        "chapter_name": row.get("chapter_name"),
        "section_no": row.get("section_no"),
        "section_name": row.get("section_name"),

        # 본문
        "text": row.get("text") or "",
        "amendment_note": row.get("amendment_note"),

        # 검색 단계
        "search_stage": row.get("search_stage"),

        # 인용
        "ref_citations_internal": _json_dumps(row.get("ref_citations_internal") or []),
        "ref_citations_external": _json_dumps(row.get("ref_citations_external") or []),
        "mentioned_laws": _json_dumps(row.get("mentioned_laws") or []),
    }


# =========================================================
# Loader
# =========================================================
import time

def load_law_jsonl_to_db(
    jsonl_paths: List[str],
    *,
    batch_size: int = 2000,
    commit_every_batches: int = 10,   # 배치 N번마다 커밋
    log_every_rows: int = 50_000      # row N개마다 로그
) -> None:
    conninfo = conninfo_from_env()

    t0 = time.time()
    total_rows = 0
    total_nodes = 0
    total_laws = 0
    batches_since_commit = 0

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            law_seen_global: set[str] = set()
            node_buffer: List[Dict[str, Any]] = []

            for jsonl_path in jsonl_paths:
                print(f"[START] {jsonl_path}", flush=True)
                file_rows = 0
                file_nodes = 0
                file_t0 = time.time()

                for row in iter_jsonl(jsonl_path):
                    total_rows += 1
                    file_rows += 1

                    # 1) laws upsert (law_id 단위 1회)
                    law_row = extract_law_row(row)
                    law_id = law_row["law_id"]
                    if law_id and law_id not in law_seen_global:
                        cur.execute(UPSERT_LAW_SQL, law_row)
                        law_seen_global.add(law_id)
                        total_laws += 1

                    # 2) law_units upsert (batch)
                    node_row = extract_node_row(row)
                    if node_row.get("doc_id"):
                        node_buffer.append(node_row)
                        total_nodes += 1
                        file_nodes += 1

                    # 배치 flush
                    if len(node_buffer) >= batch_size:
                        cur.executemany(UPSERT_LAW_UNITS_SQL, node_buffer)
                        node_buffer.clear()
                        batches_since_commit += 1

                        # 배치 단위 커밋(DEFERRABLE FK 검사/인덱스 갱신이 한 번에 몰리지 않게)
                        if batches_since_commit >= commit_every_batches:
                            conn.commit()
                            batches_since_commit = 0
                            elapsed = time.time() - t0
                            print(
                                f"[COMMIT] rows={total_rows:,} nodes={total_nodes:,} laws={total_laws:,} "
                                f"elapsed={elapsed:,.1f}s",
                                flush=True
                            )

                    # 행 단위 진행 로그 (대략적인 ‘살아있음’ 표시)
                    if (total_rows % log_every_rows) == 0:
                        elapsed = time.time() - t0
                        print(
                            f"[PROGRESS] rows={total_rows:,} nodes={total_nodes:,} laws={total_laws:,} "
                            f"buffer={len(node_buffer):,} elapsed={elapsed:,.1f}s",
                            flush=True
                        )

                # 파일 끝나면 남은 버퍼 flush + 커밋
                if node_buffer:
                    cur.executemany(UPSERT_LAW_UNITS_SQL, node_buffer)
                    node_buffer.clear()

                conn.commit()
                batches_since_commit = 0
                file_elapsed = time.time() - file_t0
                print(
                    f"[DONE] {jsonl_path} rows={file_rows:,} nodes={file_nodes:,} "
                    f"elapsed={file_elapsed:,.1f}s",
                    flush=True
                )

        # 최종 커밋은 위에서 파일마다 했지만, 안전 차원에서 한 번 더
        conn.commit()

    total_elapsed = time.time() - t0
    print(
        f"[ALL DONE] files={len(jsonl_paths)} rows={total_rows:,} nodes={total_nodes:,} laws={total_laws:,} "
        f"elapsed={total_elapsed:,.1f}s",
        flush=True
    )


# =========================================================
# Entrypoint
# =========================================================
if __name__ == "__main__":
    need_laws_path = Path(__file__).parent / "../raw/need_laws.json"
    jsonl_dir = Path(__file__).parent / "../raw/law_jsonldata"

    with need_laws_path.open("r", encoding="utf-8") as f:
        need_laws = json.load(f)

    all_paths = [jsonl_dir / f"{code}.jsonl" for code in need_laws.values()]

    existing_paths: list[str] = []
    missing_paths: list[str] = []

    for p in all_paths:
        if p.exists():
            existing_paths.append(str(p))
        else:
            missing_paths.append(str(p))

    if missing_paths:
        print("⚠️ 다음 jsonl 파일이 없어 건너뜁니다:")
        for p in missing_paths:
            print("  -", p)

    if not existing_paths:
        print("❌ 적재할 jsonl 파일이 하나도 없습니다. 종료합니다.")
    else:
        load_law_jsonl_to_db(existing_paths, batch_size=2048)

