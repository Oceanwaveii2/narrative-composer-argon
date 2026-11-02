"""
World State Port and Prototype Implementation for Narrative Node Graph (NNG).
Keeps relationship topology, locations, and facts decoupled from entity identity graphs.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import json

DEFAULT_WORLD_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "graph" / "world.json"
)


@runtime_checkable
class WorldStateProvider(Protocol):
    """Protocol defining the world state query interface for Narrative Composer."""

    def relationships(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
        canon: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries active relationships involving entity_id."""
        ...

    def facts(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
        canon: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries known ground-truth or episodic facts about entity_id."""
        ...

    def location(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
    ) -> Optional[str]:
        """Queries current physical room or zone location for entity_id."""
        ...


class PrototypeWorld:
    """
    Lightweight JSON-backed prototype implementation of WorldStateProvider.
    Reads config/graph/world.json or in-memory dictionary.
    """

    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ):
        if data is not None:
            self.data = data
        else:
            p = Path(config_path) if config_path else DEFAULT_WORLD_CONFIG
            if p.exists():
                self.data = json.loads(p.read_text(encoding="utf-8"))
            else:
                self.data = {"relationships": [], "facts": []}

    def to_dict(self) -> Dict[str, Any]:
        return self.data

    def relationships(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
        canon: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        res: List[Dict[str, Any]] = []
        target = entity_id.lower()
        for rel in self.data.get("relationships", []):
            if rel.get("a", "").lower() == target or rel.get("b", "").lower() == target:
                if canon is not None:
                    allowed_canons = rel.get("canons", [])
                    if allowed_canons and canon not in allowed_canons:
                        continue
                from_scene = rel.get("from_scene")
                if from_scene is not None and scene_index is not None and scene_index < from_scene:
                    continue
                to_scene = rel.get("to_scene")
                if to_scene is not None and scene_index is not None and scene_index > to_scene:
                    continue
                res.append(rel)
        return res

    def facts(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
        canon: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        res: List[Dict[str, Any]] = []
        target = entity_id.lower()
        for fact in self.data.get("facts", []):
            if fact.get("entity", "").lower() == target:
                if canon is not None:
                    allowed_canons = fact.get("canons", [])
                    if allowed_canons and canon not in allowed_canons:
                        continue
                res.append(fact)
        return res

    def location(
        self,
        entity_id: str,
        scene_index: Optional[int] = None,
    ) -> Optional[str]:
        target = entity_id.lower()
        locs = self.data.get("locations", {})
        if target in locs:
            val = locs[target]
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                return val.get(str(scene_index), val.get("default"))
        return None
