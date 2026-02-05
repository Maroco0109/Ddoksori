"""
똑소리 프로젝트 - 답변 후처리 모듈 (Answer Post-processor)

작성일: 2026-02-04
목적: LLM 생성 답변의 형식을 자동으로 수정

[주요 기능]
1. 헤더 형식 수정: [규정] 내용 → [규정]\n내용
2. 유사 사례 번호 추가: 사례 제목 → 1. 사례 제목
3. 출처 정보 보강: 유사 사례에 URL/PDF 출처 추가
"""

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

import psycopg2

logger = logging.getLogger(__name__)


def _get_db_connection():
    """
    PostgreSQL 데이터베이스 연결을 가져옵니다.

    Returns:
        psycopg2 connection 객체
    """
    from ...common.config import get_config

    config = get_config()
    db_config = config.database.get_connection_dict()

    return psycopg2.connect(**db_config)


@lru_cache(maxsize=1000)
def _get_pdf_url_from_db(source_file: str) -> Optional[str]:
    """
    DB에서 source_file에 대응하는 다운로드 URL을 조회합니다. (LRU 캐싱)

    Args:
        source_file: PDF 파일명 (예: "2024년 전자거래 조정사례.json")

    Returns:
        다운로드 URL 또는 None
    """
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        # 직접 매칭
        cursor.execute("""
            SELECT download_url
            FROM pdf_url_mapping
            WHERE source_file = %s
              AND is_active = TRUE
        """, (source_file,))

        result = cursor.fetchone()

        if result:
            cursor.close()
            conn.close()
            return result[0]

        # .json 확장자 제거 후 매칭
        if source_file.endswith(".json"):
            base_name = source_file[:-5]  # .json 제거
            cursor.execute("""
                SELECT download_url
                FROM pdf_url_mapping
                WHERE source_file = %s
                  AND is_active = TRUE
            """, (base_name,))

            result = cursor.fetchone()

            if result:
                cursor.close()
                conn.close()
                return result[0]

        cursor.close()
        conn.close()
        return None

    except Exception as e:
        logger.error(f"[Postprocessor] Failed to get PDF URL from DB for {source_file}: {e}")
        return None


def _get_pdf_url(source_file: str) -> Optional[str]:
    """
    source_file에 대응하는 다운로드 URL을 조회합니다.

    Args:
        source_file: PDF 파일명 (예: "2024년 전자거래 조정사례.pdf")

    Returns:
        다운로드 URL 또는 None
    """
    return _get_pdf_url_from_db(source_file)


def postprocess_answer(
    answer: str,
    retrieval: Optional[Dict[str, Any]] = None,
) -> str:
    """
    LLM 생성 답변의 형식을 후처리하여 수정합니다.

    Args:
        answer: LLM이 생성한 원본 답변
        retrieval: 검색 결과 (출처 정보 보강용)

    Returns:
        형식이 수정된 답변
    """
    if not answer:
        return answer

    logger.info(f"[Postprocessor] Input answer (first 200 chars): {answer[:200]}...")

    # Step 0: 코드 블록 마커 제거 (LLM이 ```로 감싸는 경우 대비)
    answer = _remove_code_block_markers(answer)

    # Step 1: 윗첨자 제거
    answer = _remove_superscripts(answer)

    # Step 2: 헤더 형식 수정 (헤더와 내용 사이에 줄바꿈 추가)
    answer = _fix_header_format(answer)

    # Step 3: Bullet 포인트 분리 (같은 줄에 여러 bullet이 있는 경우)
    answer = _separate_bullets(answer)

    # Step 4: [면책 문구] → [주의 사항] 변경
    answer = answer.replace("[면책 문구]", "[주의 사항]")

    # Step 5: 유사 사례 번호 → 불릿 변경
    answer = _fix_case_numbering(answer)

    # Step 6: 출처 정보 보강
    if retrieval:
        answer = _enhance_sources(answer, retrieval)

    # 최종 출처 섹션 확인
    if "[출처]" in answer:
        source_start = answer.find("[출처]")
        source_preview = answer[source_start:source_start+200]
        logger.info(f"[Postprocessor] Final source section preview: {source_preview}...")

    logger.info("[Postprocessor] Answer format corrected")
    return answer


def _remove_code_block_markers(answer: str) -> str:
    """
    LLM이 답변을 마크다운 코드 블록(```)으로 감싼 경우 제거합니다.

    Args:
        answer: 코드 블록 마커를 포함할 수 있는 답변 문자열

    Returns:
        코드 블록 마커가 제거된 답변 문자열
    """
    # 답변 시작과 끝의 공백 제거
    answer = answer.strip()

    # 코드 블록 마커로 감싸진 경우 제거
    # 패턴: ``` 또는 ```markdown 등으로 시작하고 ```로 끝나는 경우
    if answer.startswith("```"):
        lines = answer.split("\n")
        # 첫 줄이 ```로 시작하면 제거
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 마지막 줄이 ```면 제거
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        answer = "\n".join(lines)
        logger.info("[Postprocessor] Removed code block markers (```)")

    return answer.strip()


def _remove_superscripts(answer: str) -> str:
    """
    윗첨자 숫자(¹, ², ³ 등)를 제거합니다.

    Args:
        answer: 윗첨자를 포함할 수 있는 답변 문자열

    Returns:
        윗첨자가 제거된 답변 문자열
    """
    # 유니코드 윗첨자 매핑 (제거용)
    superscript_map = {
        '⁰': '', '¹': '', '²': '', '³': '', '⁴': '',
        '⁵': '', '⁶': '', '⁷': '', '⁸': '', '⁹': ''
    }

    for sup, replacement in superscript_map.items():
        if sup in answer:
            answer = answer.replace(sup, replacement)
            logger.info(f"[Postprocessor] Removed superscript: {sup}")

    return answer


def _fix_header_format(answer: str) -> str:
    """
    섹션 헤더 뒤에 내용이 같은 줄에 있으면 줄바꿈을 추가합니다.

    변환 예:
    [규정] 『전자상거래법』... → [규정]\n\n『전자상거래법』...
    [유사 사례] ● 사례 → [유사 사례]\n\n● 사례
    [출처]\n● 내용 → [출처]\n\n● 내용
    """
    headers = ["[답변 요약]", "[규정]", "[유사 사례]", "[주의 사항]", "[출처]"]

    for header in headers:
        # 패턴 1: [헤더](공백)(내용) → [헤더]\n\n(내용)
        pattern1 = re.escape(header) + r' +(.+)'

        def replace1(match):
            original = match.group(0)
            content = match.group(1)
            result = header + "\n\n" + content
            logger.info(f"[HeaderFix] Pattern1 {header}: '{original[:60]}...' → '{result[:60]}...'")
            return result

        answer = re.sub(pattern1, replace1, answer)

        # 패턴 2: [헤더]\n(내용) → [헤더]\n\n(내용)
        pattern2 = re.escape(header) + r'\n(?!\n)(.)'

        def replace2(match):
            original = match.group(0)
            first_char = match.group(1)
            result = header + "\n\n" + first_char
            logger.info(f"[HeaderFix] Pattern2 {header}: original has single \\n, adding double \\n\\n")
            return result

        answer = re.sub(pattern2, replace2, answer)

    return answer


def _separate_bullets(answer: str) -> str:
    """
    같은 줄에 여러 개의 bullet 포인트(●)가 있으면 분리합니다.

    변환 예:
    [유사 사례] ● 사례1 ● 사례2 → [유사 사례] ● 사례1\n\n● 사례2
    [출처] ● 출처1 ● 출처2 ● 출처3 → [출처] ● 출처1\n\n● 출처2\n\n● 출처3
    """
    # 줄 중간이나 공백 뒤에 나타나는 ● 앞에 double newline 추가
    # 패턴: (줄바꿈이 아닌 문자)(공백)(●) → (문자)\n\n●
    # 단, 줄 시작의 ●는 건드리지 않음
    old_answer = answer
    answer = re.sub(r'([^\n])\s+(●)', r'\1\n\n\2', answer)

    if old_answer != answer:
        logger.info("[Postprocessor] Separated bullets on the same line")

    return answer


def _fix_case_numbering(answer: str) -> str:
    """
    [유사 사례] 섹션의 항목에 불릿 포인트(●)가 없으면 추가합니다.

    변환 예:
    [유사 사례]
    사례 제목 - 결과
    다른 사례 - 결과

    →

    [유사 사례]
    ● 사례 제목 - 결과
    ● 다른 사례 - 결과
    """
    # [유사 사례] 섹션 찾기 (빈 줄 허용)
    # 패턴: [유사 사례] + 줄바꿈 + (빈줄 포함) 내용 + 다음 섹션 헤더 전까지
    case_section_pattern = r"(\[유사 사례\][ \t]*\n)([\s\S]*?)(?=\n\[|$)"

    def add_bullets(match):
        header = match.group(1)
        content = match.group(2)

        logger.info(f"[Postprocessor] Found case section, content length: {len(content)}")

        # 내용이 비어있거나 공백만 있으면 그대로 반환
        if not content.strip():
            return match.group(0)

        # 각 줄에 불릿 추가 또는 번호를 불릿으로 변경
        lines = content.split("\n")
        bulleted_lines = []
        case_count = 0
        had_content = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # 빈 줄은 그대로 유지 (첫 번째 내용 줄 이후에만)
                if had_content:
                    bulleted_lines.append("")
                continue

            had_content = True

            # 번호가 있으면 불릿으로 변경 (1. 또는 1) → ●)
            number_match = re.match(r"^\d+[\.\)]\s*(.+)", stripped)
            if number_match:
                # 번호 제거하고 불릿으로 변경
                bulleted_lines.append(f"● {number_match.group(1)}")
                case_count += 1
            elif stripped.startswith("●"):
                # 이미 불릿이면 그대로
                bulleted_lines.append(stripped)
                case_count += 1
            else:
                # 번호도 불릿도 없으면 불릿 추가
                bulleted_lines.append(f"● {stripped}")
                case_count += 1

        # 각 bullet 사이에 빈 줄 추가 (마크다운 줄바꿈을 위해)
        # header와 첫 bullet 사이에도 빈 줄 추가 (double newline)
        result = header + "\n" + "\n\n".join(bulleted_lines)
        logger.info(f"[Postprocessor] Case section bulleted: {case_count} items")
        return result

    answer = re.sub(case_section_pattern, add_bullets, answer)
    return answer


def _enhance_sources(answer: str, retrieval: Dict[str, Any]) -> str:
    """
    [출처] 섹션에 유사 사례의 URL/PDF 정보를 보강합니다.

    retrieval에서 disputes와 counsels의 출처 정보를 추출하여
    [출처] 섹션에 누락된 경우 추가합니다.
    """
    disputes = retrieval.get("disputes", [])
    counsels = retrieval.get("counsels", [])
    all_cases = disputes + counsels

    logger.info(f"[Postprocessor] Source enhancement: {len(disputes)} disputes, {len(counsels)} counsels")

    if not all_cases:
        return answer

    # 사례별 출처 정보 수집
    source_entries = []
    for i, case in enumerate(all_cases):
        title = case.get("doc_title") or case.get("title", "")
        source_org = case.get("source_org", "")
        url = case.get("url", "")
        source_file = case.get("source_file", "")
        printed_page = case.get("printed_page")

        logger.info(f"[Postprocessor] Case {i}: title={title[:30] if title else 'None'}, url={'YES' if url else 'NO'}, source_file={'YES' if source_file else 'NO'}, printed_page={printed_page}")

        if not title:
            continue

        # 출처 정보 구성 (마크다운 링크 형식, 불릿 포인트 ●)
        if url:
            # 마크다운 링크 형식 [텍스트](URL)
            if source_org:
                entry = f"● [{source_org} - {title}]({url})"
            else:
                entry = f"● [{title}]({url})"
            logger.info(f"[Postprocessor] URL source entry added")
        elif source_file:
            # PDF 파일 정보 (.json 확장자는 .pdf로 변경)
            display_file = source_file.replace(".json", ".pdf") if source_file.endswith(".json") else source_file

            # 페이지 번호가 있으면 페이지 번호 사용, 없으면 사례 번호 사용
            if printed_page:
                page_info = f", p.{printed_page}"
            else:
                # 사례 번호 찾기 (metadata에서)
                metadata = case.get("metadata", {}) if isinstance(case.get("metadata"), dict) else {}
                case_number = metadata.get("번호") or metadata.get("case_number")
                if case_number:
                    page_info = f", 사례 #{case_number}"
                else:
                    page_info = ""

            # PDF URL 조회
            pdf_url = _get_pdf_url(source_file)

            if pdf_url:
                # URL이 있으면 마크다운 링크 형식으로 (파일명에 링크 적용)
                if source_org:
                    entry = f"● [{source_org}] 『{title}』 ([{display_file}]({pdf_url}){page_info})"
                else:
                    entry = f"● 『{title}』 ([{display_file}]({pdf_url}){page_info})"
                logger.info(f"[Postprocessor] PDF source entry with URL added - url: {pdf_url[:50]}...")
            else:
                # URL이 없으면 기존 형식 유지
                if source_org:
                    entry = f"● [{source_org}] 『{title}』 ({display_file}{page_info})"
                else:
                    entry = f"● 『{title}』 ({display_file}{page_info})"
                logger.info(f"[Postprocessor] PDF source entry added (no URL) - page_info: '{page_info}' (printed_page={printed_page})")
        else:
            # URL도 PDF도 없으면 기본 형식 (하지만 기록은 함)
            logger.info(f"[Postprocessor] No URL/PDF for case: {title[:50] if title else 'untitled'}")
            if source_org:
                entry = f"● [{source_org}] {title}"
            else:
                entry = f"● {title}"

        if entry not in source_entries:
            source_entries.append(entry)

    if not source_entries:
        logger.info("[Postprocessor] No source entries collected")
        return answer

    logger.info(f"[Postprocessor] Adding {len(source_entries)} source entries")
    for entry in source_entries:
        logger.info(f"[Postprocessor] Entry: {entry[:80]}...")

    # 이미 [출처] 섹션이 있는지 확인
    has_source_section = "[출처]" in answer
    logger.info(f"[Postprocessor] Has existing source section: {has_source_section}")

    if has_source_section:
        # 기존 [출처] 섹션 전체를 새 출처로 대체
        # [출처] 이후 문서 끝까지 또는 다음 섹션([로 시작하는 줄) 전까지
        source_section_pattern = r"\[출처\][ \t]*\n[\s\S]*$"

        # 각 출처 항목 사이에 빈 줄 추가 (마크다운 줄바꿈)
        # [출처] 헤더와 첫 항목 사이에도 빈 줄 (double newline)
        new_source_section = "[출처]\n\n" + "\n\n".join(source_entries)

        old_answer = answer
        answer = re.sub(source_section_pattern, new_source_section, answer)

        if old_answer != answer:
            logger.info("[Postprocessor] Source section replaced successfully")
        else:
            logger.warning("[Postprocessor] Source section replacement FAILED - pattern not matched")
            # 패턴이 매칭 안되면 강제로 끝에 추가
            answer = answer.rstrip() + "\n\n[출처]\n\n" + "\n\n".join(source_entries)
            logger.info("[Postprocessor] Appended source section at end")
    else:
        # [출처] 섹션이 없으면 끝에 추가
        source_section = "\n\n[출처]\n\n" + "\n\n".join(source_entries)
        answer = answer.rstrip() + source_section
        logger.info("[Postprocessor] Added new source section at end")

    return answer


def format_case_with_source(
    case: Dict[str, Any],
    include_content: bool = False,
) -> str:
    """
    유사 사례를 출처 정보와 함께 포맷팅합니다.

    Args:
        case: 사례 딕셔너리
        include_content: 내용 포함 여부

    Returns:
        포맷팅된 사례 문자열
    """
    title = case.get("doc_title") or case.get("title", "제목 없음")
    source_org = case.get("source_org", "")
    url = case.get("url", "")
    source_file = case.get("source_file", "")
    printed_page = case.get("printed_page")
    content = case.get("content", "")

    # 제목 구성
    if source_org:
        formatted = f"[{source_org}] {title}"
    else:
        formatted = title

    # 출처 정보 추가
    if url:
        formatted = f"[{formatted}]({url})"
    elif source_file:
        page_info = f", p.{printed_page}" if printed_page else ""
        formatted = f"{formatted} ({source_file}{page_info})"

    # 내용 추가
    if include_content and content:
        content_preview = content[:200] + "..." if len(content) > 200 else content
        formatted += f"\n   내용: {content_preview}"

    return formatted


__all__ = [
    "postprocess_answer",
    "format_case_with_source",
]
