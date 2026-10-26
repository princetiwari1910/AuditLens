"""Template loader with Pydantic validation for safety checklist templates."""

from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from app.models import TemplateModel

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_template_file(file_path: Path) -> TemplateModel:
    """Load and validate a single JSON template file with Pydantic."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TemplateModel.model_validate(data)


@lru_cache
def load_all_templates() -> dict[str, TemplateModel]:
    """Scan and cache all templates in the templates directory."""
    templates: dict[str, TemplateModel] = {}
    if not TEMPLATES_DIR.exists():
        return templates

    for json_file in sorted(TEMPLATES_DIR.glob("*.json")):
        tmpl = load_template_file(json_file)
        templates[tmpl.id] = tmpl
    return templates


def get_template(template_id: str) -> TemplateModel | None:
    """Retrieve template by id, or None if not found."""
    return load_all_templates().get(template_id)


def list_templates() -> list[TemplateModel]:
    """Return all available templates."""
    return list(load_all_templates().values())
