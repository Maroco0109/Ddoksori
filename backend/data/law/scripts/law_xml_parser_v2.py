"""
법령 XML 파서 v2 - 계층 구조 보존

기존 law_xml_to_jsonl.ipynb의 파싱 로직을 기반으로 하되,
실제 DB 스키마에 맞게 구조화된 노드를 생성합니다.
"""
import json
import re
import xml.etree.ElementTree as ET
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
from pathlib import Path

try:
    from law_chunking_strategy import ChunkingStrategy, get_strategy_instance
except ImportError:
    # 상대 경로 import 시도
    import sys
    from pathlib import Path
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from law_chunking_strategy import ChunkingStrategy, get_strategy_instance


# ===== 정규식 패턴 =====
_WS_STRONG = re.compile(r"\s+")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_ANGLE_NOTE = re.compile(r"<[^>]+>")

_CIRCLE = {
    "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
    "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10",
}

# 섹션 추출용 정규식 (편/장/절 패턴)
_SECTION_PATTERN = re.compile(r"제(\d+)편|제(\d+)장|제(\d+)절")


def norm_ws_strong(s: Optional[str]) -> str:
    """임베딩/검색용: 모든 공백을 단일 스페이스로"""
    if not s:
        return ""
    return _WS_STRONG.sub(" ", s).strip()


def norm_ws_preserve_lines(s: Optional[str]) -> str:
    """탭/불필요 공백만 정리(원문 구조 일부 유지)"""
    if not s:
        return ""
    s = s.replace("\t", " ")
    s = _TRAILING_SPACES.sub("\n", s)
    s = _MULTI_BLANK_LINES.sub("\n\n", s)
    return s.strip()


def extract_amendment_note(text: str) -> Tuple[str, Optional[str]]:
    """본문에서 <...> 꼬리표를 추출"""
    if not text:
        return "", None

    notes = _ANGLE_NOTE.findall(text)
    cleaned = _ANGLE_NOTE.sub("", text)
    cleaned = norm_ws_strong(cleaned)

    note_str = "".join(n.strip() for n in notes if n and n.strip())
    return cleaned, (note_str if note_str else None)


def norm_no(raw: Optional[str]) -> Optional[str]:
    """항/호 번호 정규화"""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    raw = _CIRCLE.get(raw, raw)
    m = re.search(r"(\d+)", raw)
    return m.group(1) if m else raw


def norm_subitem_hangul(raw: Optional[str]) -> Optional[str]:
    """목번호 한글(가/나/다...) 유지"""
    if raw is None:
        return None
    r = raw.strip()
    if not r:
        return None
    m = re.search(r"(가|나|다|라|마|바|사|아|자|차|카|타|파|하)", r)
    return m.group(1) if m else r


def parse_section_text(text: str) -> List[str]:
    """
    섹션 텍스트에서 편/장/절 정보 추출
    
    예: "제1편 총칙\n제1장 통칙" -> ["제1편 총칙", "제1장 통칙"]
    """
    if not text:
        return []
    
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    sections = []
    
    for line in lines:
        # 편/장/절 패턴이 있는 라인만 추출
        if _SECTION_PATTERN.search(line):
            sections.append(line)
    
    return sections


def extract_chapter_no(section_path: List[str]) -> Optional[str]:
    """섹션 경로에서 장 번호 추출"""
    if not section_path:
        return None
    
    for section in section_path:
        # "제1장 통칙" -> "1"
        match = re.search(r"제(\d+)장", section)
        if match:
            return match.group(1)
    
    return None


def extract_chapter_name(section_path: List[str]) -> Optional[str]:
    """섹션 경로에서 장 이름 추출"""
    if not section_path:
        return None
    
    for section in section_path:
        # "제1장 통칙" -> "통칙"
        match = re.search(r"제\d+장\s+(.+)", section)
        if match:
            return match.group(1).strip()
    
    return None


def extract_section_no(section_path: List[str]) -> Optional[str]:
    """섹션 경로에서 절 번호 추출"""
    if not section_path:
        return None
    
    for section in section_path:
        # "제1절 능력" -> "1"
        match = re.search(r"제(\d+)절", section)
        if match:
            return match.group(1)
    
    return None


def extract_section_name(section_path: List[str]) -> Optional[str]:
    """섹션 경로에서 절 이름 추출"""
    if not section_path:
        return None
    
    for section in section_path:
        # "제1절 능력" -> "능력"
        match = re.search(r"제\d+절\s+(.+)", section)
        if match:
            return match.group(1).strip()
    
    return None


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """날짜 문자열을 DATE 형식으로 변환 (YYYY-MM-DD)"""
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip()
    # YYYYMMDD 형식인 경우
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    
    return date_str


def parse_xml_to_nodes(
    xml_path: str,
    strategy: Optional[ChunkingStrategy] = None
) -> List[Dict[str, Any]]:
    """
    XML 파일을 파싱하여 구조화된 노드 리스트로 변환
    
    Returns:
        노드 딕셔너리 리스트 (각 노드는 law_units 테이블에 적재 가능한 형식)
    """
    if strategy is None:
        strategy = get_strategy_instance()
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # 기본 정보 추출
    basic = root.find("기본정보")
    if basic is None:
        raise ValueError(f"기본정보 누락: {xml_path}")
    
    law_id = (basic.findtext("법령ID") or "").strip()
    law_name = (basic.findtext("법령명_한글") or "").strip()
    law_type = (basic.findtext("법종구분") or "").strip()
    ministry = (basic.findtext("소관부처") or "").strip()
    promulgation_date = parse_date(basic.findtext("공포일자"))
    enforcement_date = parse_date(basic.findtext("시행일자"))
    revision_type = (basic.findtext("제개정구분") or "").strip()
    
    # 법령 정보를 노드에 포함하기 위한 공통 정보
    common_law_info = {
        "law_id": law_id,
        "law_name": law_name,
        "law_type": law_type,
        "ministry": ministry,
        "revision_type": revision_type,
    }
    
    # 법령 코드 추출 (파일명에서)
    law_code = Path(xml_path).stem  # 예: "Civil_Law"
    # XML 파일명에서 확장자 제거
    if law_code.endswith('.xml'):
        law_code = law_code[:-4]
    should_extract_sections = strategy.should_extract_sections(law_code)
    
    nodes = []
    current_section_path: List[str] = []  # 현재 섹션 경로 추적
    
    # 조문단위 순회
    for a in root.findall(".//조문단위"):
        base_article_no = (a.findtext("조문번호") or "").strip()
        if not base_article_no:
            continue
        
        branch_no = (a.findtext("조문가지번호") or "").strip()
        if branch_no == "0":
            branch_no = ""
        
        article_no_display = f"제{base_article_no}조" + (f"의{branch_no}" if branch_no else "")
        article_title = norm_ws_strong(a.findtext("조문제목", "") or "")
        article_type = (a.findtext("조문여부", "") or "").strip()
        
        article_id = f"{law_id}|A{base_article_no}" + (f"|{branch_no}" if branch_no else "")
        
        # 섹션 노드 처리 (조문여부=전문) - 섹션 정보 추적 및 업데이트
        if article_type == "전문" and should_extract_sections:
            section_text = norm_ws_preserve_lines(a.findtext("조문내용", "") or "")
            sections = parse_section_text(section_text)
            
            if sections:
                # 현재 섹션 경로 업데이트
                current_section_path = sections.copy()
            continue
        
        # 일반 조문 처리
        if article_type != "조문":
            continue
        
        # 조문 본문
        article_text = norm_ws_preserve_lines(a.findtext("조문내용", "") or "")
        article_text_clean, article_note = extract_amendment_note(article_text)
        
        # 하위 요소 확인
        clauses = a.findall("항")
        direct_items = a.findall("호")
        direct_subitems = a.findall("목")
        has_children = bool(clauses or direct_items or direct_subitems)
        
        # 공통 섹션 정보 (모든 하위 노드에 상속)
        common_section_info = {
            "section_path": current_section_path.copy() if current_section_path else [],
            "chapter_no": extract_chapter_no(current_section_path),
            "chapter_name": extract_chapter_name(current_section_path),
            "section_no": extract_section_no(current_section_path),
            "section_name": extract_section_name(current_section_path),
        }
        
        # 조문 노드 (조문 레벨)
        article_node = {
            "doc_id": article_id,
            "law_id": law_id,
            "parent_id": None,  # 섹션 노드를 만들지 않으므로 항상 None
            "level": "article",
            "is_indexable": strategy.is_indexable(law_code, "article", article_no_display, has_children=has_children),
            "article_no": article_no_display,
            "article_title": article_title,
            "paragraph_no": None,
            "item_no": None,
            "subitem_no": None,
            "path": f"{law_name} {article_no_display}" + (f"({article_title})" if article_title else ""),
            "text": article_text_clean,
            "amendment_note": article_note,
            "ref_citations_internal": [],
            "ref_citations_external": [],
            "mentioned_laws": [],
            **common_section_info,
            **common_law_info,
        }
        nodes.append(article_node)
        
        # CASE 0: 조 -> 목 직접
        if not clauses and not direct_items and direct_subitems:
            for sub in direct_subitems:
                sub_no = norm_subitem_hangul(sub.findtext("목번호"))
                if not sub_no:
                    continue
                
                sub_id = f"{article_id}|M{sub_no}"
                sub_src = norm_ws_preserve_lines(sub.findtext("목내용", "") or "")
                sub_text, sub_note = extract_amendment_note(sub_src)
                if not sub_text:
                    continue
                
                sub_node = {
                    "doc_id": sub_id,
                    "law_id": law_id,
                    "parent_id": article_id,
                    "level": "subitem",
                    "is_indexable": strategy.is_indexable(law_code, "subitem", article_no_display, has_children=False),
                    "article_no": article_no_display,
                    "article_title": article_title,
                    "paragraph_no": None,
                    "item_no": None,
                    "subitem_no": sub_no,
                    "path": f"{law_name} {article_no_display} {sub_no}목",
                    "text": sub_text,
                    "amendment_note": sub_note,
                    "ref_citations_internal": [],
                    "ref_citations_external": [],
                    "mentioned_laws": [],
                    **common_section_info,
                    **common_law_info,
                }
                nodes.append(sub_node)
            continue
        
        # CASE 1: 조 -> 호 직접
        if not clauses and direct_items:
            for it in direct_items:
                item_no = norm_no(it.findtext("호번호"))
                item_id = f"{article_id}|I{item_no or 'X'}"
                
                it_src = norm_ws_preserve_lines(it.findtext("호내용", "") or "")
                it_text, it_note = extract_amendment_note(it_src)
                subs = it.findall("목")
                
                if it_text or subs:
                    item_node = {
                        "doc_id": item_id,
                        "law_id": law_id,
                        "parent_id": article_id,
                        "level": "item",
                        "is_indexable": strategy.is_indexable(law_code, "item", article_no_display, has_children=bool(subs)),
                        "article_no": article_no_display,
                        "article_title": article_title,
                        "paragraph_no": None,
                        "item_no": item_no,
                        "subitem_no": None,
                        "path": f"{law_name} {article_no_display} 제{item_no}호",
                        "text": it_text or "",
                        "amendment_note": it_note,
                        "ref_citations_internal": [],
                        "ref_citations_external": [],
                        "mentioned_laws": [],
                        **common_section_info,
                        **common_law_info,
                    }
                    nodes.append(item_node)
                
                for sub in subs:
                    sub_no = norm_subitem_hangul(sub.findtext("목번호"))
                    sub_id = f"{item_id}|M{sub_no or 'X'}"
                    
                    sub_src = norm_ws_preserve_lines(sub.findtext("목내용", "") or "")
                    sub_text, sub_note = extract_amendment_note(sub_src)
                    if not sub_text:
                        continue
                    
                    sub_node = {
                        "doc_id": sub_id,
                        "law_id": law_id,
                        "parent_id": item_id,
                        "level": "subitem",
                        "is_indexable": strategy.is_indexable(law_code, "subitem", article_no_display, has_children=False),
                        "article_no": article_no_display,
                        "article_title": article_title,
                        "paragraph_no": None,
                        "item_no": item_no,
                        "subitem_no": sub_no,
                        "path": f"{law_name} {article_no_display} 제{item_no}호 {sub_no}목",
                        "text": sub_text,
                        "amendment_note": sub_note,
                        "ref_citations_internal": [],
                        "ref_citations_external": [],
                        "mentioned_laws": [],
                        **common_section_info,
                        **common_law_info,
                    }
                    nodes.append(sub_node)
            continue
        
        # CASE 2: 일반 구조 (항이 있는 경우)
        if not clauses:
            continue
        
        for p in clauses:
            para_no = norm_no(p.findtext("항번호"))
            para_id = f"{article_id}|P{para_no or 'X'}"
            
            p_src = norm_ws_preserve_lines(p.findtext("항내용", "") or "")
            p_text, p_note = extract_amendment_note(p_src)
            
            items = p.findall("호")
            para_subitems = p.findall("목")
            
            is_shell_px = (para_no is None) and (not p_text) and (bool(items) or bool(para_subitems))
            should_write_paragraph = bool(p_text) or (para_no is not None and (bool(items) or bool(para_subitems)))
            
            if should_write_paragraph and not is_shell_px:
                para_node = {
                    "doc_id": para_id,
                    "law_id": law_id,
                    "parent_id": article_id,
                    "level": "paragraph",
                    "is_indexable": strategy.is_indexable(law_code, "paragraph", article_no_display, has_children=bool(items or para_subitems)),
                    "article_no": article_no_display,
                    "article_title": article_title,
                    "paragraph_no": para_no,
                    "item_no": None,
                    "subitem_no": None,
                    "path": f"{law_name} {article_no_display} 제{para_no}항",
                    "text": p_text,
                    "amendment_note": p_note,
                    "ref_citations_internal": [],
                    "ref_citations_external": [],
                    "mentioned_laws": [],
                    **common_section_info,
                    **common_law_info,
                }
                nodes.append(para_node)
            
            # 항 -> 목 직접
            for sub in para_subitems:
                sub_no = norm_subitem_hangul(sub.findtext("목번호"))
                sub_id = f"{para_id}|M{sub_no or 'X'}"
                
                sub_src = norm_ws_preserve_lines(sub.findtext("목내용", "") or "")
                sub_text, sub_note = extract_amendment_note(sub_src)
                if not sub_text:
                    continue
                
                sub_node = {
                    "doc_id": sub_id,
                    "law_id": law_id,
                    "parent_id": para_id,
                    "level": "subitem",
                    "is_indexable": strategy.is_indexable(law_code, "subitem", article_no_display, has_children=False),
                    "article_no": article_no_display,
                    "article_title": article_title,
                    "paragraph_no": para_no,
                    "item_no": None,
                    "subitem_no": sub_no,
                    "path": f"{law_name} {article_no_display} 제{para_no}항 {sub_no}목",
                    "text": sub_text,
                    "amendment_note": sub_note,
                    "ref_citations_internal": [],
                    "ref_citations_external": [],
                    "mentioned_laws": [],
                    **common_section_info,
                    **common_law_info,
                }
                nodes.append(sub_node)
            
            # 항 -> 호 -> 목
            for it in items:
                item_no = norm_no(it.findtext("호번호"))
                item_id = f"{para_id}|I{item_no or 'X'}"
                
                it_src = norm_ws_preserve_lines(it.findtext("호내용", "") or "")
                it_text, it_note = extract_amendment_note(it_src)
                subs = it.findall("목")
                
                if it_text or subs:
                    item_node = {
                        "doc_id": item_id,
                        "law_id": law_id,
                        "parent_id": para_id,
                        "level": "item",
                        "is_indexable": strategy.is_indexable(law_code, "item", article_no_display, has_children=bool(subs)),
                        "article_no": article_no_display,
                        "article_title": article_title,
                        "paragraph_no": para_no,
                        "item_no": item_no,
                        "subitem_no": None,
                        "path": f"{law_name} {article_no_display} 제{para_no}항 제{item_no}호",
                        "text": it_text or "",
                        "amendment_note": it_note,
                        "ref_citations_internal": [],
                        "ref_citations_external": [],
                        "mentioned_laws": [],
                        **common_section_info,
                        **common_law_info,
                    }
                    nodes.append(item_node)
                
                for sub in subs:
                    sub_no = norm_subitem_hangul(sub.findtext("목번호"))
                    sub_id = f"{item_id}|M{sub_no or 'X'}"
                    
                    sub_src = norm_ws_preserve_lines(sub.findtext("목내용", "") or "")
                    sub_text, sub_note = extract_amendment_note(sub_src)
                    if not sub_text:
                        continue
                    
                    sub_node = {
                        "doc_id": sub_id,
                        "law_id": law_id,
                        "parent_id": item_id,
                        "level": "subitem",
                        "is_indexable": strategy.is_indexable(law_code, "subitem", article_no_display, has_children=False),
                        "article_no": article_no_display,
                        "article_title": article_title,
                        "paragraph_no": para_no,
                        "item_no": item_no,
                        "subitem_no": sub_no,
                        "path": f"{law_name} {article_no_display} 제{para_no}항 제{item_no}호 {sub_no}목",
                        "text": sub_text,
                        "amendment_note": sub_note,
                        "ref_citations_internal": [],
                        "ref_citations_external": [],
                        "mentioned_laws": [],
                        **common_section_info,
                        **common_law_info,
                    }
                    nodes.append(sub_node)
    
    return nodes


if __name__ == "__main__":
    # 테스트 코드
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python law_xml_parser_v2.py <xml_path>")
        sys.exit(1)
    
    xml_path = sys.argv[1]
    nodes = parse_xml_to_nodes(xml_path)
    
    print(f"파싱 완료: {len(nodes)}개 노드")
    print("\n처음 5개 노드:")
    for i, node in enumerate(nodes[:5], 1):
        print(f"\n[{i}] {node['doc_id']}")
        print(f"  level: {node['level']}")
        print(f"  path: {node['path']}")
        print(f"  text: {node['text'][:50]}...")
