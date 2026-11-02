"""
ID grammar and utilities for the Narrative Node Graph (NNG).

Grammar: ^[a-z0-9_]+(\\.[a-z0-9_]+)*$
Patterns:
- Entity: <entity> (e.g. 'stella')
- State: <entity>.state.<slug> (e.g. 'stella.state.nerd_20')
- Transform: <entity>.xform.<from_slug>__<to_slug> (e.g. 'stella.xform.nerd_20__nerd_80')
- Annotation: ann.<target_id_with_dots>.<n>
- Run instance: run.<runid>.<entity>.inst.<n>
- Operator node: op.<type>.<n>
"""

import hashlib
import re
from typing import Any, Dict

ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


def is_valid_id(s: str) -> bool:
    """Checks whether a string strictly matches the canonical ID grammar."""
    if not isinstance(s, str) or not s:
        return False
    return bool(ID_RE.match(s))


def slugify(name: str) -> str:
    """Converts display names to clean snake_case slug identifiers.

    Non-Latin names (e.g. Chinese cues) would slugify to nothing, so they fall back to a
    deterministic hash suffix; the ID stays ASCII and stable while the display name keeps
    the original script.
    """
    if not name:
        return ""
    s = name.strip().lower()
    # Replace non-alphanumeric characters with underscores
    s = re.sub(r"[^a-z0-9]+", "_", s)
    # Strip leading and trailing underscores and collapse repeated underscores
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        s = f"u{digest}"
    return s


def state_id(entity: str, slug: str) -> str:
    """Constructs canonical state ID: <entity>.state.<slug>."""
    e = slugify(entity)
    sl = slugify(slug)
    return f"{e}.state.{sl}"


def xform_id(entity: str, from_slug: str, to_slug: str) -> str:
    """Constructs canonical transform ID: <entity>.xform.<from_slug>__<to_slug>."""
    e = slugify(entity)
    fs = slugify(from_slug)
    ts = slugify(to_slug)
    return f"{e}.xform.{fs}__{ts}"


def parse_id(s: str) -> Dict[str, Any]:
    """
    Parses a canonical ID into its structural components.
    Raises ValueError if ID is malformed or invalid.
    """
    if not is_valid_id(s):
        raise ValueError(f"Invalid ID format: {s!r}")

    parts = s.split(".")
    if len(parts) == 1:
        return {"entity": parts[0], "kind": "entity"}

    if len(parts) >= 3:
        entity = parts[0]
        kind = parts[1]
        slug = ".".join(parts[2:])

        if kind == "state":
            return {"entity": entity, "kind": "state", "slug": slug}
        elif kind == "xform":
            if "__" not in slug:
                raise ValueError(f"Transform ID must contain double-underscore '__' between state slugs: {s!r}")
            from_part, to_part = slug.split("__", 1)
            return {
                "entity": entity,
                "kind": "xform",
                "slug": slug,
                "from_slug": from_part,
                "to_slug": to_part,
            }
        else:
            return {"entity": entity, "kind": kind, "slug": slug}

    raise ValueError(f"Unrecognized ID structure: {s!r}")
