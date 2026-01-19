#!/usr/bin/env python
"""
Golden Set 추출 스크립트

기존 DB에서 평가용 샘플 데이터를 추출하여 golden_set/ 디렉토리에 저장.
각 에이전트 평가에 필요한 형식으로 변환.
"""

import os
import json
import random
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'golden_set'


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def extract_disputes(conn, limit: int = 50) -> List[Dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                d.doc_id,
                d.title,
                d.source_org,
                d.category_path,
                d.metadata->>'decision_date' as decision_date,
                c.chunk_id,
                c.chunk_type,
                c.content
            FROM documents d
            JOIN chunks c ON d.doc_id = c.doc_id
            WHERE d.doc_type = 'mediation_case'
              AND c.drop = FALSE
              AND c.embedding IS NOT NULL
              AND c.chunk_type IN ('facts', 'claims', 'mediation_outcome', 'full')
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit * 2,))  # 2x to allow filtering
        
        rows = cur.fetchall()
    
    samples = []
    seen_docs = set()
    
    for row in rows:
        if row['doc_id'] in seen_docs:
            continue
        seen_docs.add(row['doc_id'])
        
        samples.append({
            'doc_id': row['doc_id'],
            'doc_title': row['title'],
            'source_org': row['source_org'],
            'category_path': row['category_path'],
            'decision_date': row['decision_date'],
            'chunk_id': row['chunk_id'],
            'chunk_type': row['chunk_type'],
            'content': row['content'],
            'expected_retrieval': True,
        })
        
        if len(samples) >= limit:
            break
    
    return samples


def extract_counsels(conn, limit: int = 50) -> List[Dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                d.doc_id,
                d.title,
                d.source_org,
                d.category_path,
                c.chunk_id,
                c.chunk_type,
                c.content
            FROM documents d
            JOIN chunks c ON d.doc_id = c.doc_id
            WHERE d.doc_type = 'counsel_case'
              AND c.drop = FALSE
              AND c.embedding IS NOT NULL
              AND c.chunk_type IN ('qa_combined', 'problem', 'solution')
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit * 2,))
        
        rows = cur.fetchall()
    
    samples = []
    seen_docs = set()
    
    for row in rows:
        if row['doc_id'] in seen_docs:
            continue
        seen_docs.add(row['doc_id'])
        
        samples.append({
            'doc_id': row['doc_id'],
            'doc_title': row['title'],
            'source_org': row['source_org'],
            'category_path': row['category_path'],
            'chunk_id': row['chunk_id'],
            'chunk_type': row['chunk_type'],
            'content': row['content'],
            'expected_retrieval': True,
        })
        
        if len(samples) >= limit:
            break
    
    return samples


def extract_laws(conn, limit: int = 30) -> List[Dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                lu.unit_id,
                lu.law_name,
                lu.article_number,
                lu.paragraph_number,
                lu.item_number,
                lu.unit_text,
                lu.full_path
            FROM law_units lu
            WHERE lu.embedding IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
    
    return [
        {
            'unit_id': row['unit_id'],
            'law_name': row['law_name'],
            'article_number': row['article_number'],
            'paragraph_number': row['paragraph_number'],
            'item_number': row['item_number'],
            'unit_text': row['unit_text'],
            'full_path': row['full_path'],
            'expected_retrieval': True,
        }
        for row in rows
    ]


def extract_criteria(conn, limit: int = 30) -> List[Dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                cr.unit_id,
                cr.source_label,
                cr.category,
                cr.industry,
                cr.item_group,
                cr.item,
                cr.unit_text
            FROM criteria_resolution cr
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
    
    return [
        {
            'unit_id': row['unit_id'],
            'source_label': row['source_label'],
            'category': row['category'],
            'industry': row['industry'],
            'item_group': row['item_group'],
            'item': row['item'],
            'unit_text': row['unit_text'],
            'expected_retrieval': True,
        }
        for row in rows
    ]


def generate_domain_samples() -> List[Dict]:
    samples = [
        # FSS (금융)
        {'query': '보험 해약환급금이 너무 적어요', 'expected_agency': 'FSS', 'expected_restricted': True},
        {'query': '펀드 투자 원금 손실 보상받을 수 있나요', 'expected_agency': 'FSS', 'expected_restricted': True},
        {'query': '신용카드 리볼빙 이자가 너무 높아요', 'expected_agency': 'FSS', 'expected_restricted': True},
        {'query': '대출 상환 연체이자 계산이 잘못된 것 같아요', 'expected_agency': 'FSS', 'expected_restricted': True},
        {'query': '보험설계사가 설명 없이 가입시켰어요', 'expected_agency': 'FSS', 'expected_restricted': True},
        
        # K_MEDI (의료)
        {'query': '수술 후 합병증이 생겼어요', 'expected_agency': 'K_MEDI', 'expected_restricted': True},
        {'query': '병원에서 오진으로 치료가 늦어졌어요', 'expected_agency': 'K_MEDI', 'expected_restricted': True},
        {'query': '의료비 청구가 과다한 것 같아요', 'expected_agency': 'K_MEDI', 'expected_restricted': True},
        {'query': '임플란트 시술 후 문제가 생겼어요', 'expected_agency': 'K_MEDI', 'expected_restricted': True},
        {'query': '진료 기록 열람을 거부당했어요', 'expected_agency': 'K_MEDI', 'expected_restricted': True},
        
        # KOPICO (개인정보)
        {'query': '개인정보가 유출되었어요', 'expected_agency': 'KOPICO', 'expected_restricted': True},
        {'query': '동의 없이 마케팅 문자가 와요', 'expected_agency': 'KOPICO', 'expected_restricted': True},
        {'query': '정보 삭제 요청을 거부당했어요', 'expected_agency': 'KOPICO', 'expected_restricted': True},
        {'query': 'CCTV 영상을 무단으로 사용했어요', 'expected_agency': 'KOPICO', 'expected_restricted': True},
        {'query': '제3자에게 정보가 제공됐어요', 'expected_agency': 'KOPICO', 'expected_restricted': True},
        
        # KCDRC (콘텐츠)
        {'query': '게임 아이템 환불 안 해줘요', 'expected_agency': 'KCDRC', 'expected_restricted': False},
        {'query': '넷플릭스 구독 취소가 안 돼요', 'expected_agency': 'KCDRC', 'expected_restricted': False},
        {'query': '인앱결제 취소하고 싶어요', 'expected_agency': 'KCDRC', 'expected_restricted': False},
        {'query': '웹툰 이용권 환불받고 싶어요', 'expected_agency': 'KCDRC', 'expected_restricted': False},
        {'query': '음원 스트리밍 서비스 해지가 어려워요', 'expected_agency': 'KCDRC', 'expected_restricted': False},
        
        # ECMC (개인간 거래)
        {'query': '당근마켓에서 사기당했어요', 'expected_agency': 'ECMC', 'expected_restricted': False},
        {'query': '중고나라 직거래 물건이 불량이에요', 'expected_agency': 'ECMC', 'expected_restricted': False},
        {'query': '번개장터에서 허위 판매 신고', 'expected_agency': 'ECMC', 'expected_restricted': False},
        {'query': '개인 판매자가 환불을 안 해줘요', 'expected_agency': 'ECMC', 'expected_restricted': False},
        {'query': '중고거래 택배가 안 와요', 'expected_agency': 'ECMC', 'expected_restricted': False},
        
        # KCA (일반 소비자)
        {'query': '노트북 환불받고 싶어요', 'expected_agency': 'KCA', 'expected_restricted': False},
        {'query': '에어컨 AS가 제대로 안 돼요', 'expected_agency': 'KCA', 'expected_restricted': False},
        {'query': '헬스장 중도 해지하고 싶어요', 'expected_agency': 'KCA', 'expected_restricted': False},
        {'query': '가구 배송이 한 달째 안 와요', 'expected_agency': 'KCA', 'expected_restricted': False},
        {'query': '옷 교환해달라고 했는데 거절당했어요', 'expected_agency': 'KCA', 'expected_restricted': False},
    ]
    
    return samples


def generate_query_analysis_samples() -> List[Dict]:
    samples = [
        # dispute 유형
        {
            'query': '노트북 산 지 일주일 됐는데 화면이 깨져있어요 환불받고 싶어요',
            'expected_type': 'dispute',
            'expected_keywords': ['노트북', '환불', '화면'],
        },
        {
            'query': '헬스장 3개월 등록했는데 다니다가 다쳐서 해지하고 싶어요',
            'expected_type': 'dispute',
            'expected_keywords': ['헬스장', '해지', '등록'],
        },
        
        # law 유형
        {
            'query': '전자상거래법에서 청약철회 조항이 뭐예요?',
            'expected_type': 'law',
            'expected_keywords': ['전자상거래법', '청약철회', '조항'],
        },
        {
            'query': '소비자보호법 제조물책임 관련 법령 알려주세요',
            'expected_type': 'law',
            'expected_keywords': ['소비자보호법', '제조물책임', '법령'],
        },
        
        # criteria 유형
        {
            'query': '노트북 분쟁조정기준 환불 기간이 어떻게 되나요?',
            'expected_type': 'criteria',
            'expected_keywords': ['노트북', '분쟁조정기준', '환불', '기간'],
        },
        {
            'query': '에어컨 수리 보상기준이 궁금해요',
            'expected_type': 'criteria',
            'expected_keywords': ['에어컨', '수리', '보상', '기준'],
        },
        
        # general 유형
        {
            'query': '안녕하세요',
            'expected_type': 'general',
            'expected_keywords': [],
        },
        {
            'query': '감사합니다 많은 도움이 됐어요',
            'expected_type': 'general',
            'expected_keywords': [],
        },
    ]
    
    return samples


def save_golden_set(data: Dict, filename: str, subdir: str = '') -> str:
    output_path = OUTPUT_DIR / subdir if subdir else OUTPUT_DIR
    output_path.mkdir(parents=True, exist_ok=True)
    
    filepath = output_path / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description='Extract Golden Set from database')
    parser.add_argument('--disputes', type=int, default=50, help='Number of dispute samples')
    parser.add_argument('--counsels', type=int, default=50, help='Number of counsel samples')
    parser.add_argument('--laws', type=int, default=30, help='Number of law samples')
    parser.add_argument('--criteria', type=int, default=30, help='Number of criteria samples')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')
    args = parser.parse_args()
    
    random.seed(args.seed)
    
    print(f"Extracting Golden Set to {OUTPUT_DIR}")
    print("=" * 60)
    
    conn = get_connection()
    
    try:
        print(f"Extracting {args.disputes} dispute samples...")
        disputes = extract_disputes(conn, args.disputes)
        save_golden_set(
            {'samples': disputes, 'count': len(disputes), 'extracted_at': datetime.now().isoformat()},
            'disputes.json',
            'retrieval'
        )
        print(f"  -> Saved {len(disputes)} disputes")
        
        print(f"Extracting {args.counsels} counsel samples...")
        counsels = extract_counsels(conn, args.counsels)
        save_golden_set(
            {'samples': counsels, 'count': len(counsels), 'extracted_at': datetime.now().isoformat()},
            'counsels.json',
            'retrieval'
        )
        print(f"  -> Saved {len(counsels)} counsels")
        
        print(f"Extracting {args.laws} law samples...")
        laws = extract_laws(conn, args.laws)
        save_golden_set(
            {'samples': laws, 'count': len(laws), 'extracted_at': datetime.now().isoformat()},
            'laws.json',
            'retrieval'
        )
        print(f"  -> Saved {len(laws)} laws")
        
        print(f"Extracting {args.criteria} criteria samples...")
        criteria = extract_criteria(conn, args.criteria)
        save_golden_set(
            {'samples': criteria, 'count': len(criteria), 'extracted_at': datetime.now().isoformat()},
            'criteria.json',
            'retrieval'
        )
        print(f"  -> Saved {len(criteria)} criteria")
        
    finally:
        conn.close()
    
    print("\nGenerating domain classification samples...")
    domain_samples = generate_domain_samples()
    save_golden_set(
        {'samples': domain_samples, 'count': len(domain_samples), 'generated_at': datetime.now().isoformat()},
        'domain_classification.json',
        'query_analysis'
    )
    print(f"  -> Saved {len(domain_samples)} domain samples")
    
    print("\nGenerating query analysis samples...")
    query_samples = generate_query_analysis_samples()
    save_golden_set(
        {'samples': query_samples, 'count': len(query_samples), 'generated_at': datetime.now().isoformat()},
        'query_type_classification.json',
        'query_analysis'
    )
    print(f"  -> Saved {len(query_samples)} query analysis samples")
    
    print("\n" + "=" * 60)
    print("Golden Set extraction complete!")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
