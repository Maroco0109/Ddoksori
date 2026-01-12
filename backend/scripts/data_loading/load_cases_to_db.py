"""
Dispute/Counsel 데이터 ETL 파이프라인

jsonl 파일을 파싱하여 PostgreSQL documents/chunks 테이블에 적재하는 통합 파이프라인
"""
import os
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

import psycopg


def ensure_schema(conn: psycopg.Connection) -> None:
    """스키마가 존재하는지 확인 (documents, chunks 테이블)"""
    with conn.cursor() as cur:
        # 테이블 존재 여부 확인
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'documents'
            )
        """)
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "documents 테이블이 존재하지 않습니다. "
                "먼저 backend/database/schema_v2_final.sql을 실행하여 스키마를 생성하세요."
            )
        
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'chunks'
            )
        """)
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "chunks 테이블이 존재하지 않습니다. "
                "먼저 backend/database/schema_v2_final.sql을 실행하여 스키마를 생성하세요."
            )


def conninfo_from_env() -> str:
    """환경 변수에서 PostgreSQL 연결 정보 생성"""
    return (
        f"host={os.environ.get('PGHOST','localhost')} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ.get('PGDATABASE','ddoksori')} "
        f"user={os.environ.get('PGUSER','postgres')} "
        f"password={os.environ.get('PGPASSWORD','postgres')}"
    )


# SQL 쿼리 정의
UPSERT_DOCUMENT_SQL = """
INSERT INTO documents (
    doc_id, doc_type, title, source_org, category_path, url, collected_at, metadata
) VALUES (
    %(doc_id)s, %(doc_type)s, %(title)s, %(source_org)s, 
    %(category_path)s, %(url)s, %(collected_at)s, %(metadata)s
)
ON CONFLICT (doc_id) DO UPDATE SET
    doc_type = EXCLUDED.doc_type,
    title = EXCLUDED.title,
    source_org = EXCLUDED.source_org,
    category_path = EXCLUDED.category_path,
    url = EXCLUDED.url,
    collected_at = EXCLUDED.collected_at,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();
"""

UPSERT_CHUNK_SQL = """
INSERT INTO chunks (
    chunk_id, doc_id, chunk_index, chunk_total, chunk_type, 
    content, content_length
) VALUES (
    %(chunk_id)s, %(doc_id)s, %(chunk_index)s, %(chunk_total)s,
    %(chunk_type)s, %(content)s, %(content_length)s
)
ON CONFLICT (chunk_id) DO UPDATE SET
    doc_id = EXCLUDED.doc_id,
    chunk_index = EXCLUDED.chunk_index,
    chunk_total = EXCLUDED.chunk_total,
    chunk_type = EXCLUDED.chunk_type,
    content = EXCLUDED.content,
    content_length = EXCLUDED.content_length,
    updated_at = NOW();
"""


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """ISO 형식의 datetime 문자열을 파싱"""
    if not dt_str:
        return None
    try:
        # ISO 형식: "2025-12-27T17:44:25.011318+00:00"
        if '+' in dt_str or dt_str.endswith('Z'):
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(dt_str)
    except (ValueError, AttributeError):
        return None


def parse_category_path(category: Optional[str]) -> List[str]:
    """카테고리 문자열을 배열로 변환 (예: "금융 > 신용카드" -> ["금융", "신용카드"])"""
    if not category:
        return []
    return [c.strip() for c in category.split('>') if c.strip()]


def normalize_counsel_document(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Counsel jsonl 행을 documents 테이블 형식으로 정규화
    
    매핑 규칙:
    - doc_id: row['doc_id']
    - doc_type: 'counsel_case'
    - title: row['title']
    - source_org: 'consumer.go.kr' (source 필드에서 추출)
    - category_path: row['category']를 '>' 기준으로 분할
    - url: row['url']
    - collected_at: row['collected_at']를 TIMESTAMP로 변환
    - metadata: 기타 메타데이터 (case_sn, field, item, views 등)
    """
    doc_id = str(row.get('doc_id', ''))
    if not doc_id:
        return None
    
    # source_org 추출 (예: "1372 소비자 상담센터" -> "consumer.go.kr")
    source = row.get('source', '')
    source_org = 'consumer.go.kr' if '1372' in source or 'consumer.go.kr' in source else source
    
    # category_path 변환
    category = row.get('category', '')
    category_path = parse_category_path(category)
    
    # collected_at 변환
    collected_at = parse_iso_datetime(row.get('collected_at'))
    
    # metadata 구성 (기존 metadata + 추가 필드)
    metadata = row.get('metadata', {})
    if not isinstance(metadata, dict):
        metadata = {}
    
    # 추가 메타데이터 병합
    if 'case_sn' not in metadata and 'doc_id' in row:
        metadata['case_sn'] = row['doc_id']
    if 'list_meta' in row:
        metadata['list_meta'] = row['list_meta']
    
    return {
        'doc_id': doc_id,
        'doc_type': 'counsel_case',
        'title': row.get('title', ''),
        'source_org': source_org,
        'category_path': category_path,
        'url': row.get('url'),
        'collected_at': collected_at,
        'metadata': json.dumps(metadata, ensure_ascii=False)
    }


def normalize_counsel_chunk(row: Dict[str, Any], chunk_total: int) -> Dict[str, Any]:
    """
    Counsel jsonl 행을 chunks 테이블 형식으로 정규화
    
    매핑 규칙:
    - chunk_id: row['chunk_id']
    - doc_id: row['doc_id']
    - chunk_index: row['chunk_index']
    - chunk_total: 계산된 총 청크 수
    - chunk_type: row['chunk_type'] (problem, solution, full)
    - content: row['text']
    - content_length: len(row['text'])
    """
    chunk_id = row.get('chunk_id', '')
    doc_id = str(row.get('doc_id', ''))
    chunk_index = row.get('chunk_index', 0)
    chunk_type = row.get('chunk_type', '')
    content = row.get('text', '')
    
    if not chunk_id or not doc_id or not content:
        return None
    
    return {
        'chunk_id': chunk_id,
        'doc_id': doc_id,
        'chunk_index': chunk_index,
        'chunk_total': chunk_total,
        'chunk_type': chunk_type,
        'content': content,
        'content_length': len(content)
    }


def normalize_dispute_document(row: Dict[str, Any], agency: str) -> Dict[str, Any]:
    """
    Dispute jsonl 행을 documents 테이블 형식으로 정규화
    
    매핑 규칙:
    - doc_id: {agency}_{case_no}_{case_index} 또는 {agency}_{source_pdf}_{case_index} (예: "kca_16713_1")
    - doc_type: 'mediation_case'
    - title: case_no 또는 source_pdf 기반 제목 생성
    - source_org: agency를 대문자로 변환 (kca -> KCA)
    - category_path: [] (dispute는 카테고리 정보 없음)
    - url: None (dispute는 URL 정보 없음)
    - collected_at: None (dispute는 수집일 정보 없음)
    - metadata: case_no, decision_date, source_pdf, case_index 등
    """
    case_no = row.get('case_no', '')
    case_index = row.get('case_index', 0)
    
    if case_no:
        # case_no가 있으면 case_index도 포함하여 고유성 보장
        doc_id = f"{agency}_{case_no}_{case_index}"
    else:
        # case_no가 없으면 source_pdf와 case_index 조합
        source_pdf = row.get('source_pdf', '')
        if source_pdf:
            doc_id = f"{agency}_{source_pdf}_{case_index}"
        else:
            return None
    
    # source_org 변환 (kca -> KCA, ecmc -> ECMC, kcdrc -> KCDRC)
    source_org_map = {
        'kca': 'KCA',
        'ecmc': 'ECMC',
        'kcdrc': 'KCDRC'
    }
    source_org = source_org_map.get(agency.lower(), agency.upper())
    
    # title 생성 (case_no 또는 source_pdf 기반)
    title = f"분쟁조정사례 {case_no}" if case_no else f"분쟁조정사례 {source_pdf}"
    
    # metadata 구성
    metadata = {
        'agency': agency,
        'case_no': case_no,
        'case_index': row.get('case_index'),
        'source_pdf': row.get('source_pdf'),
        'decision_date': row.get('decision_date')
    }
    
    return {
        'doc_id': doc_id,
        'doc_type': 'mediation_case',
        'title': title,
        'source_org': source_org,
        'category_path': [],
        'url': None,
        'collected_at': None,
        'metadata': json.dumps(metadata, ensure_ascii=False)
    }


def normalize_dispute_chunk(row: Dict[str, Any], doc_id: str, chunk_total: int) -> Dict[str, Any]:
    """
    Dispute jsonl 행을 chunks 테이블 형식으로 정규화
    
    매핑 규칙:
    - chunk_id: {doc_id}:{section_type}:{chunk_index:04d} (예: "kca_16713:facts:0001")
    - doc_id: 정규화된 doc_id
    - chunk_index: row['chunk_index']
    - chunk_total: 계산된 총 청크 수
    - chunk_type: row['section_type'] (facts, claims, mediation_outcome, judgment 등)
    - content: row['text']
    - content_length: len(row['text'])
    """
    chunk_index = row.get('chunk_index', 0)
    section_type = row.get('section_type', '')
    content = row.get('text', '')
    
    if not content:
        return None
    
    # chunk_id 생성
    chunk_id = f"{doc_id}:{section_type}:{chunk_index:04d}"
    
    return {
        'chunk_id': chunk_id,
        'doc_id': doc_id,
        'chunk_index': chunk_index,
        'chunk_total': chunk_total,
        'chunk_type': section_type,
        'content': content,
        'content_length': len(content)
    }


def load_counsel_jsonl(
    jsonl_path: str,
    *,
    batch_size: int = 1000,
    skip_existing: bool = False,
    conn: Optional[psycopg.Connection] = None
) -> Tuple[int, int]:
    """
    Counsel jsonl 파일을 로드하여 documents/chunks 테이블에 적재
    
    Returns:
        (문서 수, 청크 수)
    """
    if conn is None:
        conninfo = conninfo_from_env()
        conn = psycopg.connect(conninfo)
        should_close = True
    else:
        should_close = False
    
    try:
        ensure_schema(conn)
        
        # 문서별 청크 수 계산
        doc_chunk_counts: Dict[str, int] = defaultdict(int)
        chunks_by_doc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        print(f"파싱 중: {jsonl_path}")
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 10000 == 0:
                    print(f"  읽는 중: {line_num}줄")
                
                try:
                    row = json.loads(line.strip())
                    doc_id = str(row.get('doc_id', ''))
                    if not doc_id:
                        continue
                    
                    chunks_by_doc[doc_id].append(row)
                    doc_chunk_counts[doc_id] = max(
                        doc_chunk_counts[doc_id],
                        row.get('chunk_index', 0) + 1
                    )
                except json.JSONDecodeError as e:
                    print(f"  경고: {line_num}줄 JSON 파싱 실패: {e}")
                    continue
        
        print(f"파싱 완료: {len(doc_chunk_counts)}개 문서, {sum(doc_chunk_counts.values())}개 청크")
        
        # 문서 메타데이터 추출 (각 문서의 첫 번째 청크에서)
        documents: Dict[str, Dict[str, Any]] = {}
        for doc_id, chunks in chunks_by_doc.items():
            if chunks:
                doc_row = normalize_counsel_document(chunks[0])
                if doc_row:
                    documents[doc_id] = doc_row
        
        # 배치로 documents 적재
        with conn.cursor() as cur:
            doc_buffer: List[Dict[str, Any]] = []
            doc_count = 0
            
            for doc_id, doc_row in documents.items():
                doc_buffer.append(doc_row)
                
                if len(doc_buffer) >= batch_size:
                    cur.executemany(UPSERT_DOCUMENT_SQL, doc_buffer)
                    doc_count += len(doc_buffer)
                    doc_buffer.clear()
                    print(f"  문서 적재 중: {doc_count}/{len(documents)}")
            
            if doc_buffer:
                cur.executemany(UPSERT_DOCUMENT_SQL, doc_buffer)
                doc_count += len(doc_buffer)
            
            conn.commit()
            print(f"문서 적재 완료: {doc_count}개")
        
        # 배치로 chunks 적재
        with conn.cursor() as cur:
            chunk_buffer: List[Dict[str, Any]] = []
            chunk_count = 0
            
            for doc_id, chunks in chunks_by_doc.items():
                chunk_total = doc_chunk_counts[doc_id]
                
                for row in chunks:
                    chunk_row = normalize_counsel_chunk(row, chunk_total)
                    if chunk_row:
                        chunk_buffer.append(chunk_row)
                    
                    if len(chunk_buffer) >= batch_size:
                        cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)
                        chunk_count += len(chunk_buffer)
                        chunk_buffer.clear()
                        if chunk_count % 10000 == 0:
                            print(f"  청크 적재 중: {chunk_count}")
            
            if chunk_buffer:
                cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)
                chunk_count += len(chunk_buffer)
            
            conn.commit()
            print(f"청크 적재 완료: {chunk_count}개")
        
        return (doc_count, chunk_count)
    
    finally:
        if should_close:
            conn.close()


def load_dispute_jsonl(
    jsonl_path: str,
    agency: str,
    *,
    batch_size: int = 1000,
    skip_existing: bool = False,
    conn: Optional[psycopg.Connection] = None
) -> Tuple[int, int]:
    """
    Dispute jsonl 파일을 로드하여 documents/chunks 테이블에 적재
    
    Args:
        jsonl_path: jsonl 파일 경로
        agency: 기관명 ('kca', 'ecmc', 'kcdrc')
    
    Returns:
        (문서 수, 청크 수)
    """
    if conn is None:
        conninfo = conninfo_from_env()
        conn = psycopg.connect(conninfo)
        should_close = True
    else:
        should_close = False
    
    try:
        ensure_schema(conn)
        
        # 문서별 청크 수 계산
        doc_chunk_counts: Dict[str, int] = defaultdict(int)
        chunks_by_doc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        print(f"파싱 중: {jsonl_path}")
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 10000 == 0:
                    print(f"  읽는 중: {line_num}줄")
                
                try:
                    row = json.loads(line.strip())
                    # doc_id 생성 (case_index 포함하여 고유성 보장)
                    case_no = row.get('case_no', '')
                    case_index = row.get('case_index', 0)
                    
                    if case_no:
                        doc_id = f"{agency}_{case_no}_{case_index}"
                    else:
                        source_pdf = row.get('source_pdf', '')
                        if source_pdf:
                            doc_id = f"{agency}_{source_pdf}_{case_index}"
                        else:
                            continue
                    
                    chunks_by_doc[doc_id].append(row)
                    doc_chunk_counts[doc_id] = max(
                        doc_chunk_counts[doc_id],
                        row.get('chunk_index', 0) + 1
                    )
                except json.JSONDecodeError as e:
                    print(f"  경고: {line_num}줄 JSON 파싱 실패: {e}")
                    continue
        
        print(f"파싱 완료: {len(doc_chunk_counts)}개 문서, {sum(doc_chunk_counts.values())}개 청크")
        
        # 문서별로 청크를 section_type과 원래 chunk_index 기준으로 정렬하여
        # 문서 전체에서 고유한 chunk_index 재부여
        # 섹션 순서: facts -> claims -> mediation_outcome -> judgment -> analysis -> 기타
        section_order = {
            'facts': 0,
            'claims': 1,
            'mediation_outcome': 2,
            'judgment': 3,
            'analysis': 4,
            'decision': 5
        }
        
        def sort_key(row: Dict[str, Any]) -> tuple:
            section_type = row.get('section_type', '')
            original_chunk_idx = row.get('chunk_index', 0)
            section_priority = section_order.get(section_type, 999)
            return (section_priority, original_chunk_idx)
        
        # 문서별 청크 재인덱싱
        reindexed_chunks: Dict[str, List[Dict[str, Any]]] = {}
        for doc_id, chunks in chunks_by_doc.items():
            # 섹션과 원래 chunk_index 기준으로 정렬
            sorted_chunks = sorted(chunks, key=sort_key)
            # 문서 전체에서 0부터 시작하는 새로운 chunk_index 부여
            for new_idx, row in enumerate(sorted_chunks):
                row['_new_chunk_index'] = new_idx
            reindexed_chunks[doc_id] = sorted_chunks
            # chunk_total 재계산
            doc_chunk_counts[doc_id] = len(sorted_chunks)
        
        # 문서 메타데이터 추출 (각 문서의 첫 번째 청크에서)
        documents: Dict[str, Dict[str, Any]] = {}
        for doc_id, chunks in reindexed_chunks.items():
            if chunks:
                doc_row = normalize_dispute_document(chunks[0], agency)
                if doc_row and doc_row['doc_id'] == doc_id:
                    documents[doc_id] = doc_row
        
        # 배치로 documents 적재
        with conn.cursor() as cur:
            doc_buffer: List[Dict[str, Any]] = []
            doc_count = 0
            
            for doc_id, doc_row in documents.items():
                doc_buffer.append(doc_row)
                
                if len(doc_buffer) >= batch_size:
                    cur.executemany(UPSERT_DOCUMENT_SQL, doc_buffer)
                    doc_count += len(doc_buffer)
                    doc_buffer.clear()
                    print(f"  문서 적재 중: {doc_count}/{len(documents)}")
            
            if doc_buffer:
                cur.executemany(UPSERT_DOCUMENT_SQL, doc_buffer)
                doc_count += len(doc_buffer)
            
            conn.commit()
            print(f"문서 적재 완료: {doc_count}개")
        
        # 배치로 chunks 적재
        with conn.cursor() as cur:
            chunk_buffer: List[Dict[str, Any]] = []
            chunk_count = 0
            
            for doc_id, chunks in reindexed_chunks.items():
                chunk_total = doc_chunk_counts[doc_id]
                
                for row in chunks:
                    # 재인덱싱된 chunk_index 사용
                    row['chunk_index'] = row['_new_chunk_index']
                    chunk_row = normalize_dispute_chunk(row, doc_id, chunk_total)
                    if chunk_row:
                        chunk_buffer.append(chunk_row)
                    
                    if len(chunk_buffer) >= batch_size:
                        cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)
                        chunk_count += len(chunk_buffer)
                        chunk_buffer.clear()
                        if chunk_count % 10000 == 0:
                            print(f"  청크 적재 중: {chunk_count}")
            
            if chunk_buffer:
                cur.executemany(UPSERT_CHUNK_SQL, chunk_buffer)
                chunk_count += len(chunk_buffer)
            
            conn.commit()
            print(f"청크 적재 완료: {chunk_count}개")
        
        return (doc_count, chunk_count)
    
    finally:
        if should_close:
            conn.close()


def main():
    """메인 함수: CLI 인터페이스"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Dispute/Counsel 데이터를 PostgreSQL에 로드')
    parser.add_argument('--counsel', type=str, help='Counsel jsonl 파일 경로')
    parser.add_argument('--dispute', type=str, help='Dispute jsonl 파일 경로')
    parser.add_argument('--agency', type=str, choices=['kca', 'ecmc', 'kcdrc'], 
                        help='Dispute 파일의 기관명 (--dispute 사용 시 필수)')
    parser.add_argument('--batch-size', type=int, default=1000, help='배치 크기 (기본값: 1000)')
    
    args = parser.parse_args()
    
    if not args.counsel and not args.dispute:
        parser.error('--counsel 또는 --dispute 중 하나는 필수입니다.')
    
    if args.dispute and not args.agency:
        parser.error('--dispute 사용 시 --agency는 필수입니다.')
    
    conninfo = conninfo_from_env()
    conn = psycopg.connect(conninfo)
    
    try:
        if args.counsel:
            print(f"\n=== Counsel 데이터 로드: {args.counsel} ===")
            doc_count, chunk_count = load_counsel_jsonl(
                args.counsel, 
                batch_size=args.batch_size,
                conn=conn
            )
            print(f"완료: {doc_count}개 문서, {chunk_count}개 청크")
        
        if args.dispute:
            print(f"\n=== Dispute 데이터 로드: {args.dispute} (기관: {args.agency}) ===")
            doc_count, chunk_count = load_dispute_jsonl(
                args.dispute,
                args.agency,
                batch_size=args.batch_size,
                conn=conn
            )
            print(f"완료: {doc_count}개 문서, {chunk_count}개 청크")
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
