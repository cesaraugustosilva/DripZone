from pathlib import Path
from uuid import uuid4


def safe_image_name(extension: str) -> str:
    ext = extension.lower().lstrip(".")
    return f"{uuid4().hex}.{ext}"


def ensure_child_path(base: Path, child: Path) -> Path:
    base_resolved = base.resolve()
    child_resolved = child.resolve()
    if base_resolved != child_resolved and base_resolved not in child_resolved.parents:
        raise ValueError("Caminho inválido.")
    return child_resolved
