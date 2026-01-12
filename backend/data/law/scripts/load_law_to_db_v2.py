"""
법령 데이터 ETL 파이프라인 v2 + S1-D2

XML 파일을 파싱하여 PostgreSQL에 적재하는 통합 파이프라인
- law_node 테이블: 법령 계층 구조 (조/항/호/목)
- documents + chunks 테이블: RAG 벡터 검색용
- chunk_relations 테이블: 법령 계층 관계
"""
import os
import json
from typing import Any, Dict, List, Optional
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import psycopg

try:
    from law_xml_parser_v2 import parse_xml_to_nodes
    from law_chunking_strategy import get_strategy_instance
except ImportError:
    # 상대 경로 import 시도
    import sys
    from pathlib import Path
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from law_xml_parser_v2 import parse_xml_to_nodes
    from law_chunking_strategy import get_strategy_instance


def conninfo_from_env() -> str:
    return (
        f"host={os.environ.get('PGHOST','localhost')} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ.get('PGDATABASE','ddoksori')} "
        f"user={os.environ.get('PGUSER','postgres')} "
        f"password={os.environ.get('PGPASSWORD','postgres')}"
    )


# 스키마 DDL (law_schema_v2.sql의 내용을 참고)
DDL_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS laws (
  law_id              TEXT PRIMARY KEY,
  law_name            TEXT NOT NULL,
  law_type            TEXT,
  ministry            TEXT,
  promulgation_date   DATE,
  enforcement_date     DATE,
  revision_type       TEXT,
  domain              TEXT
);

CREATE TABLE IF NOT EXISTS law_node (
  doc_id                 TEXT PRIMARY KEY,
  law_id                 TEXT NOT NULL REFERENCES laws(law_id) ON DELETE CASCADE,
  parent_id              TEXT REFERENCES law_node(doc_id),
  level                  TEXT NOT NULL,
  is_indexable           BOOLEAN NOT NULL DEFAULT TRUE,
  article_no             TEXT,
  article_title          TEXT,
  paragraph_no           TEXT,
  item_no                TEXT,
  subitem_no             TEXT,
  path                   TEXT,
  text                   TEXT NOT NULL,
  amendment_note         TEXT,
  section_path           JSONB DEFAULT '[]'::jsonb,
  chapter_no             TEXT,
  chapter_name           TEXT,
  section_no             TEXT,
  section_name           TEXT,
  search_stage           TEXT,
  ref_citations_internal JSONB NOT NULL DEFAULT '[]'::jsonb,
  ref_citations_external JSONB NOT NULL DEFAULT '[]'::jsonb,
  mentioned_laws         JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at             TIMESTAMP DEFAULT NOW(),
  updated_at             TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_law_node_law_id ON law_node(law_id);
CREATE INDEX IF NOT EXISTS idx_law_node_parent_id ON law_node(parent_id);
CREATE INDEX IF NOT EXISTS idx_law_node_level ON law_node(level);
CREATE INDEX IF NOT EXISTS idx_law_node_is_indexable ON law_node(is_indexable);
CREATE INDEX IF NOT EXISTS idx_law_node_law_article ON law_node(law_id, article_no);
CREATE INDEX IF NOT EXISTS idx_law_node_search_stage ON law_node(search_stage);
"""


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
  domain=COALESCE(EXCLUDED.domain, laws.domain);
"""


UPSERT_LAW_NODE_SQL = """
INSERT INTO law_node (
  doc_id, law_id, parent_id,
  level, is_indexable,
  article_no, article_title, paragraph_no, item_no, subitem_no,
  path, text, amendment_note,
  section_path, chapter_no, chapter_name, section_no, section_name, search_stage,
  ref_citations_internal, ref_citations_external, mentioned_laws
) VALUES (
  %(doc_id)s, %(law_id)s, %(parent_id)s,
  %(level)s, %(is_indexable)s,
  %(article_no)s, %(article_title)s, %(paragraph_no)s, %(item_no)s, %(subitem_no)s,
  %(path)s, %(text)s, %(amendment_note)s,
  %(section_path)s::jsonb, %(chapter_no)s, %(chapter_name)s, %(section_no)s, %(section_name)s, %(search_stage)s,
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
  text=EXCLUDED.text,
  amendment_note=EXCLUDED.amendment_note,
  section_path=EXCLUDED.section_path,
  chapter_no=EXCLUDED.chapter_no,
  chapter_name=EXCLUDED.chapter_name,
  section_no=EXCLUDED.section_no,
  section_name=EXCLUDED.section_name,
  search_stage=EXCLUDED.search_stage,
  ref_citations_internal=EXCLUDED.ref_citations_internal,
  ref_citations_external=EXCLUDED.ref_citations_external,
  mentioned_laws=EXCLUDED.mentioned_laws;
"""

# RAG 테이블용 SQL
UPSERT_DOCUMENT_SQL = """
INSERT INTO documents (
  doc_id, doc_type, title, source_org, category_path, url, metadata
) VALUES (
  %(doc_id)s, 'law', %(title)s, 'statute', %(category_path)s, %(url)s, %(metadata)s::jsonb
)
ON CONFLICT (doc_id) DO UPDATE SET
  title=EXCLUDED.title,
  category_path=EXCLUDED.category_path,
  url=EXCLUDED.url,
  metadata=EXCLUDED.metadata;
"""

UPSERT_CHUNK_SQL = """
INSERT INTO chunks (
  chunk_id, doc_id, chunk_index, chunk_total, chunk_type, content, content_length
) VALUES (
  %(chunk_id)s, %(doc_id)s, %(chunk_index)s, %(chunk_total)s, %(chunk_type)s, %(content)s, %(content_length)s
)
ON CONFLICT (chunk_id) DO UPDATE SET
  content=EXCLUDED.content,
  content_length=EXCLUDED.content_length,
  chunk_type=EXCLUDED.chunk_type;
"""

INSERT_CHUNK_RELATION_SQL = """
INSERT INTO chunk_relations (
  source_chunk_id, target_chunk_id, relation_type, confidence
) VALUES (
  %(source_chunk_id)s, %(target_chunk_id)s, %(relation_type)s, %(confidence)s
)
ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO NOTHING;
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    """스키마 생성"""
    with conn.cursor() as cur:
        cur.execute(DDL_SQL)
    conn.commit()


def extract_law_info_from_xml(xml_path: str) -> Optional[Dict[str, Any]]:
    """XML 파일에서 법령 기본 정보 직접 추출"""
    import xml.etree.ElementTree as ET
    from law_xml_parser_v2 import parse_date
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        basic = root.find("기본정보")
        if basic is None:
            return None
        
        law_id = (basic.findtext("법령ID") or "").strip()
        law_name = (basic.findtext("법령명_한글") or "").strip()
        law_type = (basic.findtext("법종구분") or "").strip()
        ministry = (basic.findtext("소관부처") or "").strip()
        promulgation_date = parse_date(basic.findtext("공포일자"))
        enforcement_date = parse_date(basic.findtext("시행일자"))
        revision_type = (basic.findtext("제개정구분") or "").strip()
        
        return {
            "law_id": law_id,
            "law_name": law_name,
            "law_type": law_type,
            "ministry": ministry,
            "promulgation_date": promulgation_date,
            "enforcement_date": enforcement_date,
            "revision_type": revision_type,
            "domain": "statute",
        }
    except Exception as e:
        print(f"경고: XML에서 법령 정보 추출 실패: {e}")
        return None


def extract_law_info(nodes: List[Dict[str, Any]], xml_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """노드 리스트에서 법령 기본 정보 추출 (XML 직접 추출 우선)"""
    # XML에서 직접 추출 시도
    if xml_path:
        law_info = extract_law_info_from_xml(xml_path)
        if law_info:
            return law_info
    
    # 노드에서 추출 (폴백)
    if not nodes:
        return None
    
    first_node = None
    for node in nodes:
        if node.get("law_id"):
            first_node = node
            break
    
    if not first_node:
        return None
    
    return {
        "law_id": first_node.get("law_id"),
        "law_name": first_node.get("law_name"),
        "law_type": first_node.get("law_type"),
        "ministry": first_node.get("ministry"),
        "promulgation_date": None,
        "enforcement_date": None,  # 노드에서 추출 불가
        "revision_type": first_node.get("revision_type"),
        "domain": "statute",
    }


def extract_law_node_row(node: Dict[str, Any]) -> Dict[str, Any]:
    """노드를 law_node 테이블 적재용 딕셔너리로 변환"""
    # search_stage 결정
    level = node.get("level", "")
    is_indexable = node.get("is_indexable", False)

    if level == "article":
        search_stage = "stage1"
    elif level in ["paragraph", "item", "subitem"] and is_indexable:
        search_stage = "stage2"
    else:
        search_stage = "stage1"  # 기본값

    return {
        "doc_id": node.get("doc_id"),
        "law_id": node.get("law_id"),
        "parent_id": node.get("parent_id"),
        "level": level,
        "is_indexable": is_indexable,
        "article_no": node.get("article_no"),
        "article_title": node.get("article_title"),
        "paragraph_no": node.get("paragraph_no"),
        "item_no": node.get("item_no"),
        "subitem_no": node.get("subitem_no"),
        "path": node.get("path"),
        "text": node.get("text", ""),
        "amendment_note": node.get("amendment_note"),
        "section_path": json.dumps(node.get("section_path") or [], ensure_ascii=False),
        "chapter_no": node.get("chapter_no"),
        "chapter_name": node.get("chapter_name"),
        "section_no": node.get("section_no"),
        "section_name": node.get("section_name"),
        "search_stage": search_stage,
        "ref_citations_internal": json.dumps(node.get("ref_citations_internal") or [], ensure_ascii=False),
        "ref_citations_external": json.dumps(node.get("ref_citations_external") or [], ensure_ascii=False),
        "mentioned_laws": json.dumps(node.get("mentioned_laws") or [], ensure_ascii=False),
    }


def create_document_for_law(law_info: Dict[str, Any]) -> Dict[str, Any]:
    """법령 정보를 documents 테이블용 딕셔너리로 변환"""
    metadata = {
        "law_type": law_info.get("law_type"),
        "ministry": law_info.get("ministry"),
        "promulgation_date": str(law_info.get("promulgation_date")) if law_info.get("promulgation_date") else None,
        "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
        "revision_type": law_info.get("revision_type"),
    }

    return {
        "doc_id": law_info["law_id"],
        "title": law_info["law_name"],
        "category_path": [],  # 법령은 category_path 없음
        "url": None,  # 나중에 법제처 URL 추가 가능
        "metadata": json.dumps(metadata, ensure_ascii=False),
    }


def create_chunk_for_node(node: Dict[str, Any], chunk_index: int, total_indexable: int) -> Optional[Dict[str, Any]]:
    """law_node를 chunks 테이블용 딕셔너리로 변환 (indexable 노드만)"""
    if not node.get("is_indexable", False):
        return None

    level = node.get("level", "")
    chunk_type_map = {
        "article": "article",
        "paragraph": "paragraph",
        "item": "item",
        "subitem": "subitem",
    }
    chunk_type = chunk_type_map.get(level, "article")

    doc_id = node.get("doc_id", "")
    text = node.get("text", "")

    # chunk_id: law_node의 doc_id를 그대로 사용 (중복 방지)
    chunk_id = doc_id

    # doc_id는 law_id (documents 테이블의 doc_id와 연결)
    law_id = node.get("law_id", "")

    return {
        "chunk_id": chunk_id,
        "doc_id": law_id,  # documents.doc_id (law_id)
        "chunk_index": chunk_index,
        "chunk_total": total_indexable,
        "chunk_type": chunk_type,
        "content": text,
        "content_length": len(text),
    }


def create_chunk_relation(parent_node: Dict[str, Any], child_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """parent-child 관계를 chunk_relations용 딕셔너리로 변환"""
    if not parent_node.get("is_indexable") or not child_node.get("is_indexable"):
        return None

    parent_level = parent_node.get("level", "")
    child_level = child_node.get("level", "")

    # relation_type 결정
    relation_type_map = {
        ("article", "paragraph"): "child_paragraph",
        ("article", "item"): "child_item",
        ("paragraph", "item"): "child_item",
        ("item", "subitem"): "child_subitem",
    }

    relation_type = relation_type_map.get((parent_level, child_level))
    if not relation_type:
        return None

    # chunk_id는 law_node의 doc_id
    parent_chunk_id = parent_node.get("doc_id")
    child_chunk_id = child_node.get("doc_id")

    if not parent_chunk_id or not child_chunk_id:
        return None

    return {
        "source_chunk_id": parent_chunk_id,
        "target_chunk_id": child_chunk_id,
        "relation_type": relation_type,
        "confidence": 1.0,
    }


def load_xml_to_db(
    xml_path: str,
    *,
    batch_size: int = 2000,
    strategy: Optional[Any] = None,
    load_rag_tables: bool = True
) -> int:
    """
    XML 파일을 파싱하여 PostgreSQL에 적재 (S1-D2: 양쪽 시스템 통합 로딩)

    Args:
        xml_path: XML 파일 경로
        batch_size: 배치 크기
        strategy: ChunkingStrategy 인스턴스 (None이면 자동 생성)
        load_rag_tables: True면 documents/chunks도 함께 로드, False면 law_node만 로드

    Returns:
        적재된 노드 수
    """
    if strategy is None:
        strategy = get_strategy_instance()

    # XML 파싱
    print(f"파싱 중: {xml_path}")
    nodes = parse_xml_to_nodes(xml_path, strategy)
    print(f"파싱 완료: {len(nodes)}개 노드")

    if not nodes:
        print("경고: 파싱된 노드가 없습니다.")
        return 0

    # 법령 기본 정보 추출
    law_info = extract_law_info(nodes, xml_path=xml_path)
    if not law_info or not law_info.get("law_id"):
        print("경고: 법령 기본 정보를 추출할 수 없습니다.")
        return 0

    # 데이터 무결성 검증: parent_id 참조 검증
    node_ids = {n.get("doc_id") for n in nodes if n.get("doc_id")}
    orphaned_nodes = []
    for node in nodes:
        parent_id = node.get("parent_id")
        if parent_id and parent_id not in node_ids:
            orphaned_nodes.append(f"{node.get('doc_id')} → parent:{parent_id}")

    if orphaned_nodes:
        print(f"⚠️  경고: {len(orphaned_nodes)}개 노드가 존재하지 않는 parent_id를 참조합니다")
        print(f"  첫 5개 예시:")
        for example in orphaned_nodes[:5]:
            print(f"    - {example}")
        print(f"  이러한 노드의 parent_id를 NULL로 설정하여 계속 진행합니다...")

        # orphaned nodes의 parent_id를 NULL로 수정
        for node in nodes:
            parent_id = node.get("parent_id")
            if parent_id and parent_id not in node_ids:
                node["parent_id"] = None

    conninfo = conninfo_from_env()

    with psycopg.connect(conninfo) as conn:
        ensure_schema(conn)

        with conn.cursor() as cur:
            # Defer foreign key constraints until end of transaction
            # This allows inserting nodes in any order
            cur.execute("SET CONSTRAINTS ALL DEFERRED;")

            # 1. 법령 정보 upsert (laws 테이블)
            print(f"  [laws] 법령 정보 적재: {law_info['law_name']}")
            cur.execute(UPSERT_LAW_SQL, law_info)

            # 2. law_node 노드 배치 적재
            # 부모를 먼저 삽입하기 위해 level별로 정렬: chapter/section → article → paragraph → item → subitem
            level_order = {
                'chapter': 0,
                'section': 1,
                'article': 2,
                'paragraph': 3,
                'item': 4,
                'subitem': 5,
            }

            def node_sort_key(node):
                """계층 순서대로 정렬 (부모 먼저)"""
                level = node.get("level", "article")
                return level_order.get(level, 99)

            sorted_nodes = sorted(nodes, key=node_sort_key)

            law_node_buffer: List[Dict[str, Any]] = []
            loaded_count = 0

            for node in sorted_nodes:
                law_node_row = extract_law_node_row(node)
                if not law_node_row["doc_id"]:
                    continue

                law_node_buffer.append(law_node_row)

                if len(law_node_buffer) >= batch_size:
                    cur.executemany(UPSERT_LAW_NODE_SQL, law_node_buffer)
                    loaded_count += len(law_node_buffer)
                    law_node_buffer.clear()
                    print(f"  [law_node] 적재 중: {loaded_count}/{len(sorted_nodes)}")

            # 남은 버퍼 flush
            if law_node_buffer:
                cur.executemany(UPSERT_LAW_NODE_SQL, law_node_buffer)
                loaded_count += len(law_node_buffer)

            print(f"  [law_node] 적재 완료: {loaded_count}개 노드")

            # 3. RAG 테이블 로딩 (documents + chunks + chunk_relations)
            if load_rag_tables:
                print(f"  [RAG] documents/chunks 적재 시작")

                # 3-1. documents 테이블 (법령당 1개)
                doc_row = create_document_for_law(law_info)
                cur.execute(UPSERT_DOCUMENT_SQL, doc_row)
                print(f"    [documents] 1개 문서 적재")

                # 3-2. chunks 테이블 (indexable 노드만)
                indexable_nodes = [n for n in nodes if n.get("is_indexable", False)]
                total_indexable = len(indexable_nodes)

                chunk_buffer: List[Dict[str, Any]] = []
                for idx, node in enumerate(indexable_nodes):
                    chunk_row = create_chunk_for_node(node, idx, total_indexable)
                    if chunk_row:
                        chunk_buffer.append(chunk_row)

                        if len(chunk_buffer) >= batch_size:
                            cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)
                            chunk_buffer.clear()

                if chunk_buffer:
                    cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)

                print(f"    [chunks] {total_indexable}개 청크 적재")

                # 3-3. chunk_relations 테이블 (parent-child 관계)
                # 노드 맵 생성 (doc_id -> node)
                node_map = {n.get("doc_id"): n for n in nodes if n.get("doc_id")}

                relation_buffer: List[Dict[str, Any]] = []
                for node in nodes:
                    parent_id = node.get("parent_id")
                    if parent_id and parent_id in node_map:
                        parent_node = node_map[parent_id]
                        relation_row = create_chunk_relation(parent_node, node)
                        if relation_row:
                            relation_buffer.append(relation_row)

                            if len(relation_buffer) >= batch_size:
                                cur.executemany(INSERT_CHUNK_RELATION_SQL, relation_buffer)
                                relation_buffer.clear()

                if relation_buffer:
                    cur.executemany(INSERT_CHUNK_RELATION_SQL, relation_buffer)

                print(f"    [chunk_relations] {len([n for n in nodes if n.get('parent_id')])}개 관계 적재")

        conn.commit()
        print(f"✓ 전체 적재 완료: {loaded_count}개 law_node 노드")
        return loaded_count


def load_multiple_xml_files(
    xml_paths: List[str],
    *,
    batch_size: int = 2000,
    load_rag_tables: bool = True
) -> Dict[str, int]:
    """
    여러 XML 파일을 일괄 적재

    Returns:
        {파일명: 적재된_노드_수} 딕셔너리
    """
    results = {}
    strategy = get_strategy_instance()

    for xml_path in xml_paths:
        if not os.path.exists(xml_path):
            print(f"경고: 파일을 찾을 수 없습니다: {xml_path}")
            results[xml_path] = 0
            continue

        try:
            count = load_xml_to_db(xml_path, batch_size=batch_size, strategy=strategy, load_rag_tables=load_rag_tables)
            results[xml_path] = count
        except Exception as e:
            print(f"오류 발생 ({xml_path}): {e}")
            import traceback
            traceback.print_exc()
            results[xml_path] = 0

    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python load_law_to_db_v2.py <xml_path> [<xml_path2> ...]")
        print("또는: python load_law_to_db_v2.py --all <rawdata_dir>")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        # 모든 XML 파일 일괄 적재
        rawdata_dir = sys.argv[2] if len(sys.argv) > 2 else "../data/law_rawdata"
        xml_files = list(Path(rawdata_dir).glob("*.xml"))
        xml_paths = [str(f) for f in xml_files]
        
        print(f"일괄 적재 시작: {len(xml_paths)}개 파일")
        results = load_multiple_xml_files(xml_paths)
        
        print("\n=== 적재 결과 ===")
        for path, count in results.items():
            print(f"{Path(path).name}: {count}개 노드")
    else:
        # 단일 파일 적재
        xml_path = sys.argv[1]
        load_xml_to_db(xml_path)
