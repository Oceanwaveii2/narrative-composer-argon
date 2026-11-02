"""
Reproduction checks for the known bugs. Run from the project root:

    python reproductions/check_bugs.py

Each check prints PASS/FAIL and a short detail. Exit code is non-zero if any fail.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.identity import entries_from_document, stabilize
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.store import build_store, to_text

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append(condition)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return condition


def kinds(text):
    return [element.node_type.name for element in FountainParser.parse(text)]


# 1. Bracketed UI readouts must not become characters.
text = "INT. ROOM - DAY\n\n[CONTAMINANTS: 0.0%]\n"
check("bracketed UI line is not a character cue", "CHARACTER" not in kinds(text))

# 2. CJK prose containing Latin capitals must not become a character (str.isupper trap).
text = "INT. ROOM - DAY\n\n今天练到这儿！准备拍 OOTD！\n"
check("CJK prose with 'OOTD' is not a character cue", "CHARACTER" not in kinds(text))

# 3. Bold SFX lines must not become characters.
text = "INT. ROOM - DAY\n\n**SMACK!**\n"
check("bold sound effect is not a character cue", "CHARACTER" not in kinds(text))

# 4. Duplicate IDs in a stale identity sidecar must never collapse two blocks.
text = "INT. ROOM - DAY\n\nA lamp.\n\nA lamp.\n"
entries = entries_from_document(parse_document(text))
entries[0]["id"] = entries[1]["id"] = "duplicate-id"
document = parse_document(text)
stabilize(document, entries)
ids = [block.id for block in document.blocks]
check("duplicate sidecar IDs are reissued", len(ids) == len(set(ids)), f"{ids}")

# 5. The node store must keep one node per block (it keys nodes by ID; duplicates vanish).
with tempfile.TemporaryDirectory() as tmp:
    manifest = Path(tmp) / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "facts": {},
                "initial_beliefs": {},
                "props": {},
                "character_locations": {},
                "room_topology": {},
                "beats": {},
            }
        ),
        encoding="utf-8",
    )
    text = "INT. ROOM - DAY\n\nA lamp.\n\nAnother lamp.\n"
    store = build_store(text=text, manifest_path=manifest, registry={}, use_cache=False)
    blocks = store.of_kind("block")
    check(
        "store keeps one node per block",
        len(blocks) == len(parse_document(text).blocks),
        f"{len(blocks)} nodes / {len(parse_document(text).blocks)} blocks",
    )

# 6. Text projection round-trips (a store edit must not lose bytes elsewhere).
source = Path("HOT_SCOOMP_COMPLETE_CHRONOLOGY.md").read_bytes().decode("utf-8")
store = build_store(registry=load_registry())
check("text projection is lossless", to_text(store) == source)

print()
print(f"{sum(RESULTS)}/{len(RESULTS)} checks passed")
sys.exit(0 if all(RESULTS) else 1)
