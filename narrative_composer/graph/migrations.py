"""
Schema Migration Engine for Narrative Node Graph (NNG).
Handles forward schema transformations for persistent definition graph files.
"""

from typing import Any, Callable, Dict
import copy

from narrative_composer.graph.models import SCHEMA_VERSION

MigrationFn = Callable[[Dict[str, Any]], Dict[str, Any]]

# Global registry of forward migrations: version N -> version N+1
MIGRATIONS: Dict[int, MigrationFn] = {}


def register_migration(from_version: int, fn: MigrationFn) -> None:
    """Registers a schema migration function for a specific schema version."""
    MIGRATIONS[from_version] = fn


def migrate(data: Dict[str, Any], target_version: int = SCHEMA_VERSION) -> Dict[str, Any]:
    """
    Sequentially applies registered schema migrations until reaching target_version.
    Returns the transformed dictionary.
    """
    migrated = copy.deepcopy(data)
    current_version = migrated.get("schema_version", 1)

    while current_version < target_version:
        if current_version not in MIGRATIONS:
            raise ValueError(
                f"No migration registered from schema_version {current_version} to {current_version + 1}"
            )
        migrated = MIGRATIONS[current_version](migrated)
        current_version = migrated.get("schema_version", current_version + 1)

    return migrated
