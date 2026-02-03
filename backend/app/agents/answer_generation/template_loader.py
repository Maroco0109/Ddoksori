"""
Template loader for MD prompt templates.

Loads templates from prompts/ directory and renders them with variable substitution.
Implements singleton caching for performance.
"""

import logging
import re
import threading
from pathlib import Path
from typing import Dict, Optional

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
