"""
출력 포맷터 - CLI 결과 표시
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class OutputFormatter:
    """응답 포맷터"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def format_response(self, response: Dict[str, Any], request: Dict[str, Any]) -> str:
        """
        응답을 포맷팅된 문자열로 변환

        Args:
            response: ChatResponse 딕셔너리
            request: 원본 요청 딕셔너리

        Returns:
            포맷팅된 출력 문자열
        """
        lines = []
        lines.append("=" * 80)
        lines.append(self._format_request_info(request, response.get('session_id', '')))
        lines.append(self._format_node_timings(response.get('node_timings', [])))
        lines.append(self._format_retrieval_summary(response))
        lines.append(self._format_answer(response.get('answer', '')))
        lines.append(self._format_sources(response.get('sources', [])))

        if self.verbose:
            lines.append(self._format_verbose_details(response))

        lines.append("=" * 80)
        return "\n".join(lines)

    def _format_request_info(self, request: Dict[str, Any], session_id: str) -> str:
        """요청 정보 포맷"""
        return f"""[요청 정보]
  세션 ID: {session_id}
  질문: {request.get('message', '')}
  상담 유형: {request.get('chat_type', 'general')}
"""

    def _format_node_timings(self, timings: Optional[List[Dict[str, Any]]]) -> str:
        """에이전트 타이밍 테이블 포맷"""
        if not timings:
            return "[에이전트 실행 정보]\n  타이밍 정보 없음\n"

        header = "  +-----------------+-------------+----------------------+"
        header_row = "  | {:<15} | {:>11} | {:>20} |"

        lines = ["[에이전트 실행 정보]", header]
        lines.append(header_row.format("에이전트", "소요시간", "시작"))
        lines.append(header)

        total_ms = 0
        for t in timings:
            duration = t.get('duration_ms', 0)
            total_ms += duration
            start = self._format_time(t.get('start_time', ''))
            lines.append(header_row.format(
                t.get('node_name', ''),
                f"{duration:.2f}ms",
                start
            ))

        lines.append(header)
        lines.append(f"  총 소요시간: {total_ms/1000:.2f}초\n")
        return "\n".join(lines)

    def _format_time(self, iso_time: str) -> str:
        """ISO 시간 문자열을 HH:MM:SS.mmm 형식으로 변환"""
        if not iso_time:
            return ""
        try:
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            return dt.strftime("%H:%M:%S.%f")[:-3]
        except Exception:
            return iso_time[:20] if len(iso_time) > 20 else iso_time

    def _format_retrieval_summary(self, response: Dict[str, Any]) -> str:
        """검색 결과 요약 포맷"""
        domain = response.get('domain') or {}
        similar_cases = response.get('similar_cases') or {}
        laws = response.get('related_laws') or []
        criteria = response.get('related_criteria') or []

        disputes = similar_cases.get('disputes', []) if similar_cases else []
        counsels = similar_cases.get('counsels', []) if similar_cases else []

        agency = domain.get('agency', '-') if domain else '-'
        confidence = domain.get('confidence', 0) if domain else 0

        return f"""[검색 결과 요약]
  - 추천 기관: {agency} (신뢰도: {confidence:.2f})
  - 분쟁조정 사례: {len(disputes)}건
  - 상담 사례: {len(counsels)}건
  - 관련 법령: {len(laws)}건
  - 분쟁해결 기준: {len(criteria)}건
"""

    def _format_answer(self, answer: str) -> str:
        """답변 포맷"""
        if not answer:
            return "[답변]\n  (답변 없음)\n"

        # 긴 답변은 들여쓰기 처리
        lines = answer.split('\n')
        formatted_lines = ['  ' + line for line in lines]
        return "[답변]\n" + "\n".join(formatted_lines) + "\n"

    def _format_sources(self, sources: List[Dict[str, Any]]) -> str:
        """출처 정보 포맷"""
        if not sources:
            return "[출처]\n  출처 정보 없음\n"

        lines = ["[출처]"]
        for i, src in enumerate(sources, 1):
            doc_id = src.get('doc_id', 'N/A')
            title = src.get('doc_title', src.get('title', 'N/A'))
            sim = src.get('similarity', 0)
            source_type = src.get('type', src.get('doc_type', ''))
            lines.append(f"  [{i}] {doc_id} - {title} (유사도: {sim:.2f}) [{source_type}]")
        return "\n".join(lines) + "\n"

    def _format_verbose_details(self, response: Dict[str, Any]) -> str:
        """상세 정보 포맷 (verbose 모드)"""
        lines = ["\n[상세 정보]"]

        # 분쟁조정 사례 상세
        similar_cases = response.get('similar_cases') or {}
        disputes = similar_cases.get('disputes', [])
        if disputes:
            lines.append("  분쟁조정 사례:")
            for i, d in enumerate(disputes[:3], 1):
                lines.append(f"    [{i}] {d.get('doc_id', '')} - {d.get('doc_title', '')}")
                lines.append(f"        기관: {d.get('source_org', '')} | 유사도: {d.get('similarity', 0):.2f}")

        # 상담 사례 상세
        counsels = similar_cases.get('counsels', [])
        if counsels:
            lines.append("  상담 사례:")
            for i, c in enumerate(counsels[:3], 1):
                lines.append(f"    [{i}] {c.get('doc_id', '')} - {c.get('doc_title', '')}")
                lines.append(f"        유사도: {c.get('similarity', 0):.2f}")

        # 법령 상세
        laws = response.get('related_laws') or []
        if laws:
            lines.append("  관련 법령:")
            for i, law in enumerate(laws[:3], 1):
                lines.append(f"    [{i}] {law.get('law_name', '')} {law.get('full_path', '')}")
                lines.append(f"        유사도: {law.get('similarity', 0):.2f}")

        # 기준 상세
        criteria = response.get('related_criteria') or []
        if criteria:
            lines.append("  분쟁해결 기준:")
            for i, c in enumerate(criteria[:3], 1):
                lines.append(f"    [{i}] {c.get('category', '')} > {c.get('item', '')}")
                lines.append(f"        유사도: {c.get('similarity', 0):.2f}")

        return "\n".join(lines) + "\n"
