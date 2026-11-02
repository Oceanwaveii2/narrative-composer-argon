"""
Entity and State Registry Loader for Narrative Node Graph (NNG).
Loads character definitions from JSON files with schema validation.
"""

from pathlib import Path
from typing import Dict, Optional
import json

from narrative_composer.graph.models import EntityDef

DEFAULT_CHARACTERS_DIR = (
    Path(__file__).resolve().parent.parent / "config" / "graph" / "characters"
)


def load_entity(path: Path) -> EntityDef:
    """Loads and validates a single EntityDef from a JSON file."""
    if not path.is_file():
        raise FileNotFoundError(f"Entity definition file not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    return EntityDef.model_validate_json(raw_text)


def load_registry(
    dir_path: Optional[Path] = None,
    include_auto: bool = True,
) -> Dict[str, EntityDef]:
    """
    Loads all EntityDef files from the characters directory and its auto/ subdirectory.
    Returns a dictionary mapping entity_id to EntityDef, sorted alphabetically by entity_id.
    Raises ValueError if duplicate entity IDs are encountered across files.
    """
    target_dir = Path(dir_path) if dir_path is not None else DEFAULT_CHARACTERS_DIR
    if not target_dir.exists() or not target_dir.is_dir():
        return {}

    registry: Dict[str, EntityDef] = {}
    origin_files: Dict[str, Path] = {}

    # Discover main character definition files (*.json)
    json_files = sorted(list(target_dir.glob("*.json")))

    # Also discover auto-discovered character definition files (auto/*.json)
    if include_auto:
        auto_dir = target_dir / "auto"
        if auto_dir.exists() and auto_dir.is_dir():
            json_files.extend(sorted(list(auto_dir.glob("*.json"))))

    for json_file in json_files:
        entity = load_entity(json_file)
        eid = entity.entity_id

        if eid in registry:
            first_path = origin_files[eid]
            raise ValueError(
                f"Duplicate entity_id {eid!r} found in {json_file.name!r} (already defined in {first_path.name!r})"
            )

        registry[eid] = entity
        origin_files[eid] = json_file

    # Return sorted by entity_id
    return {k: registry[k] for k in sorted(registry.keys())}
