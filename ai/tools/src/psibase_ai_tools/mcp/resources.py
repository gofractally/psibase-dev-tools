import os
from pathlib import Path
from typing import Iterable

from .paths import AI_TOOLS_ROOT


RESOURCE_ROOTS = {
    "skills": Path(os.environ.get("AI_TOOLS_SKILLS_DIR", str(AI_TOOLS_ROOT / "skills"))),
    "knowledge": Path(os.environ.get("AI_TOOLS_KNOWLEDGE_DIR", str(AI_TOOLS_ROOT / "knowledge"))),
    "lessons-learned": Path(os.environ.get("AI_TOOLS_LESSONS_DIR", str(AI_TOOLS_ROOT / "lessons-learned"))),
}


def iter_resources() -> Iterable[dict[str, str]]:
    for kind, root in RESOURCE_ROOTS.items():
        if not root.is_dir():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            yield {
                "uri": f"ai-tools://{kind}/{rel}",
                "name": f"{kind}/{rel}",
                "mimeType": "text/markdown" if path.suffix in {".md", ".markdown"} else "text/plain",
                "path": str(path),
            }


def path_for_uri(uri: str) -> Path:
    if not uri.startswith("ai-tools://"):
        raise ValueError(f"Unsupported resource URI: {uri}")
    rest = uri[len("ai-tools://") :]
    kind, _, rel = rest.partition("/")
    root = RESOURCE_ROOTS.get(kind)
    if root is None:
        raise ValueError(f"Unsupported resource root: {kind}")
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Resource URI escapes root: {uri}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Resource not found: {uri}")
    return path


def read_resource(uri: str) -> str:
    return path_for_uri(uri).read_text(encoding="utf-8", errors="replace")
