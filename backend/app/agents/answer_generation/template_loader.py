"""
Template loader for MD prompt templates.

Loads templates from prompts/ directory and renders them with variable substitution.
Implements singleton caching for performance.
"""

import logging
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
_template_lock = threading.Lock()
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class _SafeFormatDict(dict):
    """Dict that returns the original placeholder for missing keys in format_map."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class TemplateLoader:
    """Loads and renders MD prompt templates with variable substitution."""

    _instance: Optional["TemplateLoader"] = None
    _templates: Optional[Dict[str, str]] = None
    REQUIRED_TEMPLATES = {"solution", "action", "execution", "fallback", "base"}

    def __new__(cls) -> "TemplateLoader":
        """Singleton pattern - thread-safe with double-checked locking."""
        if cls._instance is None:
            with _template_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize template loader (loads templates on first call)."""
        if self._templates is None:
            with _template_lock:
                if self._templates is None:
                    self._templates = self._load_all_prompts()

    def _load_all_prompts(self) -> Dict[str, str]:
        """Load all prompt templates from prompts/ directory.

        Returns:
            Dictionary mapping template keys to their content.
        """
        template_files = {
            "base": "base_persona.md",
            "solution": "solution_template.md",
            "inquiry": "inquiry_template.md",
            "action": "action_guide_template.md",
            "execution": "execution_guide_template.md",
            "fallback": "fallback_template.md",
            "reject": "reject_template.md",
        }

        loaded = {}
        # Use __file__ to get absolute path to prompts directory
        current_dir = Path(__file__).parent
        prompts_dir = current_dir / "prompts"

        for key, filename in template_files.items():
            full_path = prompts_dir / filename
            if full_path.exists():
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        loaded[key] = f.read()
                    logger.debug(f"Loaded template '{key}' from {full_path}")
                except Exception as e:
                    if key in self.REQUIRED_TEMPLATES:
                        logger.error(
                            f"Required template '{key}' failed to load from {full_path}: {e}"
                        )
                        raise RuntimeError(
                            f"Required template '{key}' failed to load: {e}"
                        ) from e
                    else:
                        logger.warning(
                            f"Failed to read template '{key}' from {full_path}: {e}"
                        )
                        loaded[key] = ""
            else:
                if key in self.REQUIRED_TEMPLATES:
                    logger.error(f"Required template file not found: {full_path}")
                    raise RuntimeError(f"Required template file not found: {full_path}")
                else:
                    logger.warning(f"Template file not found: {full_path}")
                    loaded[key] = ""

        return loaded

    def render(self, template_key: str, context: Dict[str, str]) -> str:
        """Render a template with variable substitution.

        First replaces {base_persona} with base template content,
        then replaces all other variables from context.

        Args:
            template_key: Key identifying the template to render.
            context: Dictionary of variable names to values.

        Returns:
            Rendered template string, or empty string if template not found.
        """
        if self._templates is None:
            logger.error("Templates not loaded")
            return ""

        # Get base persona template
        base = self._templates.get("base", "")

        # Get the requested template
        raw_template = self._templates.get(template_key, "")
        if not raw_template:
            logger.warning(f"Template '{template_key}' not found or empty")
            return ""

        # First, replace base_persona placeholder
        template = raw_template.replace("{base_persona}", base)

        # Build safe context for format_map (preserves unsubstituted vars)
        safe_context = _SafeFormatDict({k: str(v) for k, v in context.items()})
        try:
            template = template.format_map(safe_context)
        except (KeyError, ValueError, IndexError) as e:
            logger.warning(
                f"Template '{template_key}' format_map failed: {e}, falling back to manual substitution"
            )
            for key, val in context.items():
                placeholder = f"{{{key}}}"
                template = template.replace(placeholder, str(val))

        # Check for any remaining unsubstituted placeholders
        remaining_placeholders = _PLACEHOLDER_RE.findall(template)
        if remaining_placeholders:
            logger.warning(
                f"Template '{template_key}' has unsubstituted variables: {remaining_placeholders}"
            )

        return template


# Module-level constants for followup extraction
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DYNAMIC_TEMPLATES = {"inquiry", "reject"}
_TEMPLATE_TO_FILE = {
    "solution": "solution_template.md",
    "action": "action_guide_template.md",
    "execution": "execution_guide_template.md",
    "fallback": "fallback_template.md",
}
_FOLLOWUP_SECTION_RE = re.compile(r"## 🔘 추가 안내.*?\n([\s\S]*?)(?=\n##|\Z)")

# LLM 응답에서 추가 질문 추출용 패턴
_RESPONSE_FOLLOWUP_PATTERN = re.compile(
    r"추가로 궁금하신 점이 있으시면[:\s]*\n((?:\s*-\s*.+\n?)+)",
    re.MULTILINE,
)


@lru_cache(maxsize=16)
def extract_followup_questions(template_key: str) -> List[str]:
    """
    프롬프트 파일에서 '🔘 버튼형 역질문' 섹션의 질문들을 추출합니다.

    Args:
        template_key: 템플릿 키 (예: "solution", "action", "execution")

    Returns:
        추가 질문 리스트 (최대 3개)

    Note:
        - inquiry 템플릿은 LLM이 동적으로 질문을 생성하므로 빈 배열 반환
        - reject 템플릿은 base_persona의 대체 질문 사용하므로 빈 배열 반환
    """
    # inquiry와 reject는 동적 생성이므로 제외 (기존 로직 사용)
    if template_key in _DYNAMIC_TEMPLATES:
        return []  # 빈 배열 → generator의 기존 로직으로 fallback

    filename = _TEMPLATE_TO_FILE.get(template_key)
    if not filename:
        return []

    filepath = _PROMPTS_DIR / filename
    if not filepath.exists():
        logger.warning(f"Template file not found for followup extraction: {filepath}")
        return []

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read template for followup extraction: {e}")
        return []

    # "🔘 버튼형 역질문" 섹션 찾기
    match = _FOLLOWUP_SECTION_RE.search(content)
    if not match:
        return []

    section = match.group(1).strip()

    # 각 줄에서 질문 추출 (빈 줄, 주석, 괄호 안내 제외)
    questions = []
    for line in section.split("\n"):
        line = line.strip()
        # 빈 줄, 괄호로 시작하는 안내문, 주석 제외
        if line and not line.startswith("(") and not line.startswith("#"):
            questions.append(line)

    return questions[:3]  # 최대 3개


def extract_followup_from_response(response: str) -> tuple:
    """
    LLM 응답에서 추가 질문을 추출하고 답변에서 제거합니다.

    LLM이 "추가로 궁금하신 점이 있으시면:" 형식으로 생성한 질문을
    답변 텍스트에서 분리하여 별도의 followup_questions로 반환합니다.

    Args:
        response: LLM이 생성한 전체 응답 텍스트

    Returns:
        tuple: (clean_answer, followup_questions)
            - clean_answer: 질문 섹션이 제거된 깔끔한 답변 텍스트
            - followup_questions: 추출된 질문 리스트 (최대 3개)

    Example:
        >>> response = '''
        ... 환불 받으실 수 있습니다.
        ...
        ... 추가로 궁금하신 점이 있으시면:
        ... - 더 쉽게 설명해 드릴까요?
        ... - 메시지 초안을 작성해 드릴까요?
        ... '''
        >>> answer, questions = extract_followup_from_response(response)
        >>> print(answer)  # "환불 받으실 수 있습니다."
        >>> print(questions)  # ["더 쉽게 설명해 주세요?", "메시지 초안을 작성해 주세요?"]
    """
    match = _RESPONSE_FOLLOWUP_PATTERN.search(response)
    if not match:
        return response, []

    # 질문 추출
    questions_block = match.group(1)
    questions = []
    for line in questions_block.strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            q = line[2:].strip()
            # "~해 드릴까요?" → "~해 주세요" 변환 (버블 UI용 - 더 자연스러운 요청 형태)
            q = q.replace("드릴까요?", "주세요").replace("드릴게요?", "주세요")
            # 물음표 정규화
            if not q.endswith("?"):
                q = q.rstrip(".") + "?"
            questions.append(q)

    # 답변에서 질문 섹션 제거
    clean_answer = response[: match.start()].rstrip()

    return clean_answer, questions[:3]
