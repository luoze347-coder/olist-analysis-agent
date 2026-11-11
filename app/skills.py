"""Load the project's reviewed analysis skill into the agent prompt."""

from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "ecommerce-analysis" / "SKILL.md"


def load_analysis_skill(path: Path = SKILL_PATH) -> str:
    """Read one bundled skill; reject an incomplete or unexpected file."""
    text = path.read_text(encoding="utf-8")
    if len(text) > 12_000 or not text.startswith("---\n"):
        raise ValueError("Analysis skill is missing metadata or exceeds the size limit")
    parts = text.split("---\n", 2)
    if len(parts) != 3 or "name: ecommerce-analysis" not in parts[1]:
        raise ValueError("Analysis skill metadata is invalid")
    body = parts[2].strip()
    if not body:
        raise ValueError("Analysis skill instructions are empty")
    return body
