"""
법령 청킹 전략 (S1-D2 Default Strategy)

법령 노드의 indexable 여부 및 섹션 추출 규칙을 정의합니다.
"""

class ChunkingStrategy:
    """법령 청킹 전략 기본 구현"""

    def should_extract_sections(self, law_code: str) -> bool:
        """
        섹션(편/장/절) 정보를 추출할지 여부

        Args:
            law_code: 법령 코드 (예: "E_Commerce_Consumer_Law")

        Returns:
            True면 섹션 정보 추출, False면 생략
        """
        # 기본값: 모든 법령에서 섹션 추출
        return True

    def is_indexable(
        self,
        law_code: str,
        level: str,
        article_no_display: str = None,
        has_children: bool = False
    ) -> bool:
        """
        특정 노드를 검색 인덱스에 포함할지 여부

        Args:
            law_code: 법령 코드
            level: 노드 수준 ('article', 'paragraph', 'item', 'subitem')
            article_no_display: 조문 번호
            has_children: 하위 노드 존재 여부

        Returns:
            True면 indexable (chunks 테이블에 포함), False면 제외
        """
        # S1-D2 기본 전략: 모든 조/항/호/목을 indexable로 설정
        # 이유: RAG 시스템에서 최대한 세밀한 검색 지원

        if level in ('article', 'paragraph', 'item', 'subitem'):
            return True

        # chapter, section 등 구조 노드는 indexable하지 않음
        return False


def get_strategy_instance() -> ChunkingStrategy:
    """
    청킹 전략 인스턴스 생성

    Returns:
        ChunkingStrategy 인스턴스
    """
    return ChunkingStrategy()
