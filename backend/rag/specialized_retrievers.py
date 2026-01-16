"""
똑소리 프로젝트 - 전문 검색기 (Specialized Retrievers)
작성일: 2026-01-13
법령, 기준, 사례의 2단계 계층 검색 지원
"""

import psycopg2
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import requests


@dataclass
class LawSearchResult:
    """법령 검색 결과"""
    unit_id: str
    law_id: str
    law_name: str
    level: str  # article, paragraph, item, subitem
    article_no: str
    paragraph_no: Optional[str]
    item_no: Optional[str]
    subitem_no: Optional[str]
    full_path: str  # 예: "제14조 제1항"
    text: str
    similarity: float


@dataclass
class CriteriaSearchResult:
    """기준 검색 결과"""
    unit_id: str
    source_id: str
    source_label: str
    category: Optional[str]
    industry: Optional[str]
    item_group: Optional[str]
    item: Optional[str]
    dispute_type: Optional[str]
    unit_text: str
    similarity: float


class LawRetriever:
    """
    법령 2단계 검색기

    Stage 1: 항/호/목 (search_stage='stage2') 유사도 검색
    Stage 2: 매칭된 노드의 상위 조(article) 찾기
    """

    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn = None

    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성"""
        try:
            response = requests.post(
                self.embed_api_url,
                json={"texts": [query]},
                timeout=10
            )
            response.raise_for_status()
            return response.json()['embeddings'][0]
        except requests.exceptions.RequestException as e:
            raise Exception(f"임베딩 API 오류: {e}")

    def search_two_stage(self, query: str, top_k: int = 3) -> List[LawSearchResult]:
        """
        2단계 법령 검색

        1단계: law_units에서 search_stage='stage2' (항/호/목) 벡터 검색
        2단계: 매칭된 항/호/목의 상위 조(article) 정보 포함

        Returns:
            List[LawSearchResult]: 법령명, 조항호목, 본문 포함
        """
        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            # 최적화: 벡터 검색 먼저 수행 후 조인
            # pgvector 인덱스 활용을 위해 chunks 테이블에서 먼저 검색
            cur.execute(
                """
                WITH vector_search AS (
                    SELECT
                        chunk_id,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM chunks
                    WHERE embedding IS NOT NULL
                      AND drop = FALSE
                      AND chunk_id LIKE '%%|A%%'
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                )
                SELECT
                    lu.doc_id,
                    lu.law_id,
                    l.law_name,
                    lu.level,
                    lu.article_no,
                    lu.paragraph_no,
                    lu.item_no,
                    lu.subitem_no,
                    lu.path,
                    lu.text,
                    vs.similarity
                FROM vector_search vs
                JOIN law_units lu ON vs.chunk_id = lu.doc_id
                JOIN laws l ON lu.law_id = l.law_id
                WHERE lu.search_stage = 'stage2'
                ORDER BY vs.similarity DESC
                """,
                (query_embedding, query_embedding, top_k * 10)
            )

            results = []
            seen_articles = set()  # 중복 조문 제거

            for row in cur.fetchall():
                # 동일 조문 중복 방지 (가장 유사한 항/호/목만 유지)
                article_key = (row[1], row[4])  # (law_id, article_no)
                if article_key in seen_articles:
                    continue
                seen_articles.add(article_key)

                results.append(LawSearchResult(
                    unit_id=row[0],
                    law_id=row[1],
                    law_name=row[2],
                    level=row[3],
                    article_no=row[4],
                    paragraph_no=row[5],
                    item_no=row[6],
                    subitem_no=row[7],
                    full_path=row[8] or self._build_path(row[4], row[5], row[6], row[7]),
                    text=row[9],
                    similarity=float(row[10])
                ))

                if len(results) >= top_k:
                    break

            return results

    def _build_path(
        self,
        article_no: str,
        paragraph_no: Optional[str],
        item_no: Optional[str],
        subitem_no: Optional[str]
    ) -> str:
        """조항호목 경로 문자열 생성"""
        path_parts = []
        if article_no:
            path_parts.append(f"제{article_no}조" if not article_no.startswith("제") else article_no)
        if paragraph_no:
            path_parts.append(f"제{paragraph_no}항")
        if item_no:
            path_parts.append(f"제{item_no}호")
        if subitem_no:
            path_parts.append(f"{subitem_no}목")
        return " ".join(path_parts)

    def search_by_article(self, law_id: str, article_no: str) -> List[Dict]:
        """특정 조문의 모든 하위 노드 조회"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    lu.doc_id,
                    lu.level,
                    lu.paragraph_no,
                    lu.item_no,
                    lu.subitem_no,
                    lu.path,
                    lu.text
                FROM law_units lu
                WHERE
                    lu.law_id = %s
                    AND lu.article_no = %s
                ORDER BY
                    CASE lu.level
                        WHEN 'article' THEN 1
                        WHEN 'paragraph' THEN 2
                        WHEN 'item' THEN 3
                        WHEN 'subitem' THEN 4
                    END,
                    lu.paragraph_no, lu.item_no, lu.subitem_no
                """,
                (law_id, article_no)
            )

            return [
                {
                    'doc_id': row[0],
                    'level': row[1],
                    'paragraph_no': row[2],
                    'item_no': row[3],
                    'subitem_no': row[4],
                    'path': row[5],
                    'text': row[6]
                }
                for row in cur.fetchall()
            ]


class CriteriaRetriever:
    """
    분쟁조정기준 2단계 검색기

    Stage 1: criteria_units에서 search_stage='stage2' 벡터 검색
    Stage 2: 상위 카테고리/품목 정보 매핑
    """

    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn = None

    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성"""
        try:
            response = requests.post(
                self.embed_api_url,
                json={"texts": [query]},
                timeout=10
            )
            response.raise_for_status()
            return response.json()['embeddings'][0]
        except requests.exceptions.RequestException as e:
            raise Exception(f"임베딩 API 오류: {e}")

    def search_two_stage(self, query: str, top_k: int = 3) -> List[CriteriaSearchResult]:
        """
        2단계 기준 검색

        1단계: chunks 테이블에서 criteria 관련 벡터 검색
        2단계: documents 테이블에서 doc_type으로 source_label 추출

        Returns:
            List[CriteriaSearchResult]: 기준명, 카테고리, 품목, 본문 포함
        """
        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ch.chunk_id,
                    ch.doc_id,
                    d.doc_type,
                    d.title,
                    ch.content,
                    1 - (ch.embedding <=> %s::vector) AS similarity
                FROM chunks ch
                JOIN documents d ON ch.doc_id = d.doc_id
                WHERE ch.embedding IS NOT NULL
                  AND ch.drop = FALSE
                  AND d.doc_type LIKE 'criteria_%%'
                ORDER BY ch.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k * 3)
            )

            results = []
            for row in cur.fetchall():
                chunk_id = row[0]
                doc_id = row[1]
                doc_type = row[2]
                title = row[3]
                content = row[4]
                similarity = float(row[5])

                source_label = self._get_source_label(doc_type)

                results.append(CriteriaSearchResult(
                    unit_id=chunk_id,
                    source_id=doc_id,
                    source_label=source_label,
                    category=title,
                    industry=None,
                    item_group=None,
                    item=None,
                    dispute_type=None,
                    unit_text=content,
                    similarity=similarity
                ))

            return results[:top_k]

    def _get_source_label(self, doc_type: str) -> str:
        """doc_type에서 사람이 읽기 좋은 source_label 생성"""
        labels = {
            'criteria_table1': '소비자분쟁해결기준 별표1 (품목별 분류)',
            'criteria_table2': '소비자분쟁해결기준 별표2 (일반적 기준)',
            'criteria_table3': '소비자분쟁해결기준 별표3 (품목별 기준)',
            'criteria_table4': '소비자분쟁해결기준 별표4 (특수거래)',
            'criteria_content_guideline': '콘텐츠이용자보호지침',
            'criteria_ecommerce_guideline': '전자상거래 소비자보호지침',
        }
        return labels.get(doc_type, doc_type)

    def search_by_category(
        self,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        item_group: Optional[str] = None,
        top_k: int = 10
    ) -> List[CriteriaSearchResult]:
        """카테고리/산업/품목그룹으로 기준 검색"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    cu.unit_id,
                    cu.source_id,
                    c.source_label,
                    cu.category,
                    cu.industry,
                    cu.item_group,
                    cu.item,
                    cu.dispute_type,
                    cu.unit_text,
                    1.0 AS similarity
                FROM criteria_units cu
                JOIN criteria c ON cu.source_id = c.source_id
                WHERE
                    (%s IS NULL OR cu.category = %s)
                    AND (%s IS NULL OR cu.industry = %s)
                    AND (%s IS NULL OR cu.item_group = %s)
                LIMIT %s
                """,
                (category, category, industry, industry, item_group, item_group, top_k)
            )

            return [
                CriteriaSearchResult(
                    unit_id=row[0],
                    source_id=row[1],
                    source_label=row[2],
                    category=row[3],
                    industry=row[4],
                    item_group=row[5],
                    item=row[6],
                    dispute_type=row[7],
                    unit_text=row[8],
                    similarity=float(row[9])
                )
                for row in cur.fetchall()
            ]


class CaseRetriever:
    """
    사례 분리 검색기

    dispute (분쟁조정사례)와 counsel (상담사례)를 분리하여 검색
    """

    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn = None

    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성"""
        try:
            response = requests.post(
                self.embed_api_url,
                json={"texts": [query]},
                timeout=10
            )
            response.raise_for_status()
            return response.json()['embeddings'][0]
        except requests.exceptions.RequestException as e:
            raise Exception(f"임베딩 API 오류: {e}")

    def _search_by_doc_type(
        self,
        query: str,
        doc_type: str,
        top_k: int = 3
    ) -> List[Dict]:
        """특정 doc_type으로 검색"""
        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.chunk_type,
                    c.content,
                    d.title,
                    d.source_org,
                    d.url,
                    d.metadata,
                    1 - (c.embedding <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE
                    d.doc_type = %s
                    AND c.embedding IS NOT NULL
                    AND c.drop = FALSE
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, doc_type, query_embedding, top_k)
            )

            results = []
            for row in cur.fetchall():
                metadata = row[7] if row[7] else {}
                results.append({
                    'chunk_id': row[0],
                    'doc_id': row[1],
                    'chunk_type': row[2],
                    'content': row[3],
                    'doc_title': row[4],
                    'source_org': row[5],
                    'url': row[6],
                    'decision_date': metadata.get('decision_date'),
                    'similarity': float(row[8])
                })

            return results

    def search_disputes(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        분쟁조정사례 검색 (doc_type='mediation_case')

        법적 효력이 있는 분쟁조정 결과
        """
        return self._search_by_doc_type(query, 'mediation_case', top_k)

    def search_counsels(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        상담사례 검색 (doc_type='counsel_case')

        참고용 상담 사례
        """
        return self._search_by_doc_type(query, 'counsel_case', top_k)

    def search_both(self, query: str, dispute_k: int = 3, counsel_k: int = 3) -> Dict[str, List[Dict]]:
        """
        분쟁조정사례와 상담사례 동시 검색

        Returns:
            {
                'disputes': [...],
                'counsels': [...]
            }
        """
        return {
            'disputes': self.search_disputes(query, dispute_k),
            'counsels': self.search_counsels(query, counsel_k)
        }


class AgencyClassifier:
    """
    추천 기관 분류기

    분쟁 유형에 따라 적절한 기관 추천:
    - KCA (한국소비자원): 1:N 일반 소비자 분쟁
    - ECMC (전자거래분쟁조정위원회): 1:1 개인간 거래
    - KCDRC (콘텐츠분쟁조정위원회): 콘텐츠 관련 분쟁
    """

    # 콘텐츠 관련 키워드 (KCDRC)
    CONTENT_KEYWORDS = [
        "게임", "영화", "콘텐츠", "앱", "어플", "애플리케이션",
        "음악", "웹툰", "만화", "동영상", "영상", "스트리밍",
        "OTT", "넷플릭스", "왓챠", "디즈니", "유튜브",
        "인앱", "결제", "아이템", "캐시", "다이아", "루비",
        "디지털", "다운로드", "구독", "VOD", "e북", "전자책"
    ]

    # 개인간 거래 키워드 (ECMC)
    INDIVIDUAL_KEYWORDS = [
        "중고", "직거래", "당근", "당근마켓", "번개장터", "중고나라",
        "개인간", "개인거래", "개인 판매", "개인판매자",
        "직접 거래", "직접거래", "만나서", "택배거래",
        "중고거래", "중고 거래", "세컨핸드", "second hand"
    ]

    # 기관 정보
    AGENCIES = {
        'KCA': {
            'name': '한국소비자원',
            'full_name': '한국소비자원 소비자분쟁조정위원회',
            'description': '일반 소비자 분쟁 조정 (사업자 대 소비자)',
            'url': 'https://www.kca.go.kr'
        },
        'ECMC': {
            'name': '전자거래분쟁조정위원회',
            'full_name': '전자거래분쟁조정위원회',
            'description': '전자거래 및 개인간 거래 분쟁 조정',
            'url': 'https://www.ecmc.or.kr'
        },
        'KCDRC': {
            'name': '콘텐츠분쟁조정위원회',
            'full_name': '콘텐츠분쟁조정위원회',
            'description': '콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정',
            'url': 'https://www.kcdrc.kr'
        }
    }

    def classify(self, query: str) -> Dict:
        """
        질문을 분석하여 적절한 기관 추천

        Args:
            query: 사용자 질문

        Returns:
            {
                'agency': 'KCA' | 'ECMC' | 'KCDRC',
                'agency_info': {...},
                'dispute_type': '1:N' | '1:1' | 'contents',
                'reason': '추천 이유',
                'confidence': 0.0 ~ 1.0,
                'matched_keywords': [...]  # 매칭된 키워드 목록
            }
        """
        query_lower = query.lower()

        # 콘텐츠 관련 키워드 체크
        content_matches = [kw for kw in self.CONTENT_KEYWORDS if kw in query_lower]
        if content_matches:
            return {
                'agency': 'KCDRC',
                'agency_info': self.AGENCIES['KCDRC'],
                'dispute_type': 'contents',
                'reason': f"콘텐츠 관련 분쟁으로 판단됩니다 (키워드: {', '.join(content_matches[:3])})",
                'confidence': min(0.6 + len(content_matches) * 0.1, 1.0),
                'matched_keywords': content_matches
            }

        # 개인간 거래 키워드 체크
        individual_matches = [kw for kw in self.INDIVIDUAL_KEYWORDS if kw in query_lower]
        if individual_matches:
            return {
                'agency': 'ECMC',
                'agency_info': self.AGENCIES['ECMC'],
                'dispute_type': '1:1',
                'reason': f"개인간 거래 분쟁으로 판단됩니다 (키워드: {', '.join(individual_matches[:3])})",
                'confidence': min(0.6 + len(individual_matches) * 0.1, 1.0),
                'matched_keywords': individual_matches
            }

        # 기본값: KCA (일반 소비자 분쟁)
        return {
            'agency': 'KCA',
            'agency_info': self.AGENCIES['KCA'],
            'dispute_type': '1:N',
            'reason': '일반 소비자 분쟁으로 판단됩니다 (사업자 대 소비자)',
            'confidence': 0.7,
            'matched_keywords': []
        }


class StructuredRetriever:
    """
    4개 섹션 통합 검색기

    1. 추천 기관 (AgencyClassifier)
    2. 유사 사례 (CaseRetriever)
    3. 관련 법령 (LawRetriever)
    4. 관련 기준 (CriteriaRetriever)
    """

    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        self.db_config = db_config
        self.embed_api_url = embed_api_url

        self.agency_classifier = AgencyClassifier()
        self.case_retriever = CaseRetriever(db_config, embed_api_url)
        self.law_retriever = LawRetriever(db_config, embed_api_url)
        self.criteria_retriever = CriteriaRetriever(db_config, embed_api_url)

    def connect(self):
        """모든 retriever 연결"""
        self.case_retriever.connect()
        self.law_retriever.connect()
        self.criteria_retriever.connect()

    def close(self):
        """모든 retriever 연결 종료"""
        self.case_retriever.close()
        self.law_retriever.close()
        self.criteria_retriever.close()

    def search_all_sections(
        self,
        query: str,
        dispute_k: int = 3,
        counsel_k: int = 3,
        law_k: int = 3,
        criteria_k: int = 3
    ) -> Dict:
        """
        4개 섹션 데이터 일괄 검색

        Returns:
            {
                'agency': {...},          # 추천 기관
                'disputes': [...],        # 분쟁조정사례
                'counsels': [...],        # 상담사례
                'laws': [...],            # 관련 법령
                'criteria': [...]         # 관련 기준
            }
        """
        # 1. 기관 분류
        agency_result = self.agency_classifier.classify(query)

        # 2. 사례 검색
        cases = self.case_retriever.search_both(query, dispute_k, counsel_k)

        # 3. 법령 검색
        law_results = self.law_retriever.search_two_stage(query, law_k)

        # 4. 기준 검색
        criteria_results = self.criteria_retriever.search_two_stage(query, criteria_k)

        return {
            'agency': agency_result,
            'disputes': cases['disputes'],
            'counsels': cases['counsels'],
            'laws': [
                {
                    'unit_id': r.unit_id,
                    'law_name': r.law_name,
                    'full_path': r.full_path,
                    'text': r.text,
                    'similarity': r.similarity
                }
                for r in law_results
            ],
            'criteria': [
                {
                    'unit_id': r.unit_id,
                    'source_label': r.source_label,
                    'category': r.category,
                    'industry': r.industry,
                    'item_group': r.item_group,
                    'item': r.item,
                    'unit_text': r.unit_text,
                    'similarity': r.similarity
                }
                for r in criteria_results
            ]
        }
