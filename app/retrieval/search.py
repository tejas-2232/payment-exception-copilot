"""Small lexical retriever over versioned fictional procedure paragraphs."""
from pathlib import Path
import re

from app.schemas import Evidence

PROCEDURES_DIR = Path(__file__).resolve().parents[2] / "data" / "procedures"


def words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower())) - {
        "the", "a", "an", "of", "if", "is", "and", "for", "to", "in", "it"
    }


def search_procedures(query: str, directory: Path | None = None) -> list[Evidence]:
    query_words = words(query)
    if not query_words:
        return []
    ranked = []
    for path in sorted((directory or PROCEDURES_DIR).glob("*.md")):
        parts = path.read_text(encoding="utf-8").strip().split("\n\n")
        header = parts[0].splitlines()
        if len(header) < 2 or not header[0].startswith(f"# {path.stem}: ") or not header[1].startswith("Version: "):
            raise ValueError(f"Invalid procedure header: {path.name}")
        section = header[0].split(": ", 1)[1]
        version = header[1].removeprefix("Version: ").strip()
        for index, paragraph in enumerate(parts[1:], 1):
            excerpt = paragraph.strip()
            score = len(query_words & words(section + " " + excerpt))
            if score:
                ranked.append((score, Evidence(document_id=path.stem,
                    passage_id=f"{path.stem}-{index:03d}", section=section,
                    version=version, excerpt=excerpt)))
    ranked.sort(key=lambda item: (-item[0], item[1].passage_id))
    return [evidence for _, evidence in ranked]
