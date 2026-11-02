"""
Autonomous Character and State Discovery for Narrative Node Graph (NNG).
Discovers new entities and physical forms directly from ingested screenplay ASTs,
producing verified atomic patch operations and persistent JSON models.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import re

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.ids import is_valid_id, slugify, state_id, xform_id
from narrative_composer.graph.models import (
    EntityDef,
    StateDef,
    TransformDef,
    SCHEMA_VERSION,
)
from narrative_composer.graph.patch import apply_patch
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType

DEFAULT_DISCOVERY_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "graph" / "triggers" / "discovery.json"
)
DEFAULT_AUTO_DIR = (
    Path(__file__).resolve().parent.parent / "config" / "graph" / "characters" / "auto"
)


class DiscoveryResult:
    """Holds candidate entities, states, transforms, and generated patch operations."""

    def __init__(self):
        self.new_entities: List[Dict[str, Any]] = []
        self.new_states: List[Dict[str, Any]] = []
        self.new_xforms: List[Dict[str, Any]] = []
        self.new_aliases: List[Dict[str, Any]] = []
        self.patch_ops: List[Dict[str, Any]] = []
        self.skipped: List[Dict[str, Any]] = []


def _normalize_name(name: str) -> str:
    """Strips all non-alphanumeric characters and uppercases for deduplication."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def load_discovery_config(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads discovery thresholds and token dictionaries from JSON config."""
    p = Path(cfg_path) if cfg_path else DEFAULT_DISCOVERY_CONFIG
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "ignore_cues": ["GPS VOICE", "NARRATOR", "ALL", "ANNOUNCER", "TV", "RADIO", "CROWD", "BOTH"],
        "sound_words": ["CRACK", "BRAAAP", "GURGLE", "BANG", "THUD", "SMASH", "BOOM", "POP", "WHIZZ", "SLAM", "BEEP"],
        "heading_words": ["INT", "EXT", "DAY", "NIGHT", "MORNING", "EVENING", "CONTINUOUS", "LATER", "CUT", "FADE", "IN", "OUT", "TO", "SAME"],
        "relation_words": ["MOM", "MOTHER", "DAD", "FATHER", "FRIEND", "SISTER", "BROTHER", "BOSS", "NANA", "PAPA"],
        "transform_verbs": ["transforms", "turns", "morphs", "shrinks", "swells", "grows", "reshapes", "becomes", "changes"],
        "max_new_entities_per_run": 25,
        "max_new_states_per_run": 25,
        "min_state_confidence": 0.5,
    }


def discover(
    elements: List[ASTElement],
    graph: StoryGraph,
    canon: str,
    run_id: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> DiscoveryResult:
    """
    Pure analysis pass over screenplay AST elements.
    Detects uncatalogued characters and new states for known characters.
    Returns a DiscoveryResult containing transactional patch operations without mutating graph.
    """
    config = cfg or load_discovery_config()
    res = DiscoveryResult()

    ignore_cues = set(config.get("ignore_cues", []))
    sound_words = set(config.get("sound_words", []))
    heading_words = set(config.get("heading_words", []))
    relation_words = set(config.get("relation_words", []))
    transform_verbs = set(config.get("transform_verbs", []))
    max_entities = config.get("max_new_entities_per_run", 25)
    max_states = config.get("max_new_states_per_run", 25)
    min_state_confidence = config.get("min_state_confidence", 0.5)

    resolver_unconstrained = EntityResolver(graph, canon=None)

    # Collect existing entity names and normalized keys
    existing_normalized: Set[str] = set()
    for eid, ent in graph.entities.items():
        existing_normalized.add(_normalize_name(ent.display_name))
        for a in ent.aliases:
            existing_normalized.add(_normalize_name(a))
        for st in ent.states:
            for ca in st.cue_aliases:
                existing_normalized.add(_normalize_name(ca.cue))

    # Track current state for known entities to construct valid transforms
    current_state_by_entity: Dict[str, str] = {}
    for eid, ent in graph.entities.items():
        current_state_by_entity[eid] = ent.base_state

    # 1. Discover New States on Known Entities
    discovered_state_slugs: Set[Tuple[str, str]] = set()

    for el in elements:
        if el.node_type == ASTNodeType.CHARACTER:
            cue_raw = el.content.strip()
            clean_cue = cue_raw
            for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
                clean_cue = clean_cue.replace(suffix, "").strip()

            # Rule 1: Cue with explicit hyphen form marker: KNOWN-FORM (e.g. RAINEE-PETER)
            if "-" in clean_cue and not any(rel in clean_cue.upper().split("-") for rel in relation_words):
                prefix, form_part = clean_cue.split("-", 1)
                prefix_clean = prefix.strip()
                form_clean = form_part.strip()
                eid, _ = resolver_unconstrained.resolve_cue(prefix_clean)

                if eid and form_clean and form_clean not in ["CONT'D", "OS", "VO"]:
                    form_slug = slugify(form_clean)
                    ent = graph.entities[eid]
                    known_slugs = {s.slug for s in ent.states} | {s[1] for s in discovered_state_slugs if s[0] == eid}

                    if form_slug not in known_slugs and len(res.new_states) < max_states:
                        discovered_state_slugs.add((eid, form_slug))
                        new_st_id = state_id(eid, form_slug)
                        from_st_slug = current_state_by_entity[eid]
                        new_xf_id = xform_id(eid, from_st_slug, form_slug)

                        state_dict = {
                            "id": new_st_id,
                            "slug": form_slug,
                            "label": f"{form_clean.title()} {ent.display_name} Persona",
                            "order": len(ent.states) + len([s for s in res.new_states if s["entity"] == eid]) + 1,
                            "canons": [canon],
                            "cue_aliases": [{"cue": clean_cue.upper(), "state": form_slug, "canons": [canon]}],
                            "attributes": {
                                "origin": "auto",
                                "provisional": True,
                                "confidence": 0.9,
                                "discovered_at_line": el.line_number,
                                "evidence": clean_cue,
                            },
                        }
                        res.new_states.append({"entity": eid, "state": state_dict})
                        res.patch_ops.append({"op": "add_state", "entity": eid, "state": state_dict})

                        if from_st_slug != form_slug:
                            xf_dict = {
                                "id": new_xf_id,
                                "from_state": state_id(eid, from_st_slug),
                                "to_state": new_st_id,
                                "triggers": ["discovered"],
                                "reversible": False,
                                "canons": [canon],
                                "attributes": {"origin": "auto"},
                            }
                            res.new_xforms.append({"entity": eid, "xform": xf_dict})
                            res.patch_ops.append({"op": "add_xform", "entity": eid, "xform": xf_dict})

                        current_state_by_entity[eid] = form_slug

        elif el.node_type == ASTNodeType.ACTION:
            action_text = el.content
            # Rule 2: Action line transformation sentence
            # e.g., "Rainee transforms into a bloated Peter"
            verb_pattern = r"\b(" + "|".join(re.escape(v) for v in transform_verbs) + r")\s+(?:into|to|as|like)\s+([^.,;\n]+)"
            m = re.search(verb_pattern, action_text, re.IGNORECASE)
            if m:
                obj_phrase = m.group(2).strip()
                # Strip leading articles
                obj_clean = re.sub(r"^(?:an?|the)\s+", "", obj_phrase, flags=re.IGNORECASE).strip()
                words = obj_clean.split()
                if 1 <= len(words) <= 5:
                    label = " ".join(words[:5])
                    st_slug = slugify(" ".join(words[:4]))
                    # Find subject entity mentioned in action
                    for eid, ent in graph.entities.items():
                        all_names = [ent.display_name] + ent.aliases
                        if any(re.search(r"\b" + re.escape(n) + r"\b", action_text, re.IGNORECASE) for n in all_names):
                            known_slugs = {s.slug for s in ent.states} | {s[1] for s in discovered_state_slugs if s[0] == eid}
                            if st_slug not in known_slugs and len(res.new_states) < max_states:
                                confidence = 0.6
                                if confidence >= min_state_confidence:
                                    discovered_state_slugs.add((eid, st_slug))
                                    new_st_id = state_id(eid, st_slug)
                                    from_st_slug = current_state_by_entity[eid]
                                    new_xf_id = xform_id(eid, from_st_slug, st_slug)

                                    state_dict = {
                                        "id": new_st_id,
                                        "slug": st_slug,
                                        "label": label.title(),
                                        "order": len(ent.states) + len([s for s in res.new_states if s["entity"] == eid]) + 1,
                                        "canons": [canon],
                                        "attributes": {
                                            "origin": "auto",
                                            "provisional": True,
                                            "confidence": confidence,
                                            "discovered_at_line": el.line_number,
                                            "evidence": action_text[:120],
                                        },
                                    }
                                    res.new_states.append({"entity": eid, "state": state_dict})
                                    res.patch_ops.append({"op": "add_state", "entity": eid, "state": state_dict})

                                    if from_st_slug != st_slug:
                                        xf_dict = {
                                            "id": new_xf_id,
                                            "from_state": state_id(eid, from_st_slug),
                                            "to_state": new_st_id,
                                            "triggers": ["discovered"],
                                            "reversible": False,
                                            "canons": [canon],
                                            "attributes": {"origin": "auto"},
                                        }
                                        res.new_xforms.append({"entity": eid, "xform": xf_dict})
                                        res.patch_ops.append({"op": "add_xform", "entity": eid, "xform": xf_dict})

                                    current_state_by_entity[eid] = st_slug
                                else:
                                    res.skipped.append({"type": "state", "slug": st_slug, "confidence": confidence})
                            break

    # 2. Discover New Character Entities
    discovered_entities: Dict[str, Dict[str, Any]] = {}
    cue_dialogue_counts: Dict[str, int] = defaultdict(int)
    # Function words, pronouns, quantifiers, deictics and abstract nouns that are
    # never character names on their own. Guards both cue and ALL-CAPS discovery.
    stop_words = {
        "A", "AN", "THE", "IN", "ON", "AT", "TO", "OF", "AND", "OR", "BUT", "BY",
        "FOR", "WITH", "FROM", "AS", "IF", "SO", "NO", "NOT", "YES", "OK",
        "I", "ME", "MY", "MINE", "YOU", "YOUR", "HE", "HIM", "HIS", "SHE", "HER",
        "HERS", "IT", "ITS", "WE", "US", "OUR", "THEY", "THEM", "THEIR",
        "THIS", "THAT", "THESE", "THOSE", "THERE", "HERE", "WHERE", "WHEN",
        "WHY", "HOW", "WHAT", "WHO", "WHICH", "EVERYWHERE", "ANYWHERE",
        "SOMEWHERE", "NOWHERE", "NEVER", "ALWAYS", "AGAIN", "STILL", "JUST",
        "EVEN", "ONLY", "VERY", "REALLY", "RIGHT", "LEFT", "NOW", "THEN",
        "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
        "TEN", "TOTAL", "FAILURE", "SUCCESS", "ALL", "SOME", "ANY", "MORE",
        "MOST", "MUCH", "MANY", "UP", "DOWN", "OUT", "OFF", "OVER", "UNDER",
    }

    # First tally dialogue following cues
    for idx, el in enumerate(elements):
        if el.node_type == ASTNodeType.CHARACTER:
            cue = el.content.strip()
            for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
                cue = cue.replace(suffix, "").strip()
            # Look ahead for dialogue
            if idx + 1 < len(elements) and elements[idx + 1].node_type == ASTNodeType.DIALOGUE:
                cue_dialogue_counts[cue] += 1

    # Candidate source A: Unresolved cues with >= 1 dialogue line
    for cue, count in cue_dialogue_counts.items():
        if len(discovered_entities) >= max_entities:
            break
        if cue.upper() in ignore_cues or cue.upper() in stop_words:
            continue
        words = cue.split()
        if len(words) > 3 or not words:
            continue
        if any(w.upper() in sound_words or w.upper() in heading_words or w.upper() in stop_words for w in words):
            continue

        norm = _normalize_name(cue)
        if norm in existing_normalized:
            continue

        eid, _ = resolver_unconstrained.resolve_cue(cue)
        if eid is None:
            # Candidate passes
            discovered_entities[norm] = {
                "name": cue,
                "confidence": 0.9,
                "line": 0,
                "evidence": f"Dialogue speaker cue '{cue}'",
            }
            existing_normalized.add(norm)

    # Candidate source B: ALL-CAPS mentions in action lines with mixed-case occurrence
    full_text = "\n".join(e.content for e in elements)
    for el in elements:
        if el.node_type == ASTNodeType.ACTION and len(discovered_entities) < max_entities:
            action_text = el.content
            # Find runs of 1 to 3 uppercase words (e.g. "STAN SMITH", "BAH-BAH")
            # Word can contain letters and hyphens
            caps_matches = re.finditer(r"\b([A-Z][A-Z0-9]*(?:[- ][A-Z0-9]+){0,2})\b", action_text)
            for cm in caps_matches:
                caps_cand = cm.group(1).strip()
                tokens = [t for t in re.split(r"[- ]+", caps_cand) if t]
                if not tokens or len(tokens) > 3:
                    continue
                if any(w.upper() in sound_words or w.upper() in heading_words or w.upper() in stop_words for w in tokens):
                    continue
                if any(len(w) < 2 for w in tokens):
                    continue

                # A character introduction names someone and then says what they do:
                # "... BAH-BAH sits marooned ...". Shouted fragments and stage noise
                # ("Cheese EVERYWHERE.", "AHH! MY ANKLE!") end in punctuation instead.
                if not re.match(r"\s+[a-z]", action_text[cm.end():]):
                    continue

                # ...and it opens a clause, rather than sitting mid-phrase
                # ("Her breasts DROP with a heavy jiggle").
                prefix = action_text[: cm.start()].rstrip()
                if prefix and not re.search(r'[.!?:;,\u2014\u2013"\u201c]$', prefix):
                    continue

                norm = _normalize_name(caps_cand)
                if norm in existing_normalized:
                    continue

                res_eid, _ = resolver_unconstrained.resolve_cue(caps_cand)
                if res_eid is not None:
                    continue

                # Check if mixed-case version appears in text or as a cue
                # e.g., Stan drops... or Bah Bah... or Bah-Bah...
                mixed_patterns = [
                    r"\b" + r"[- ]?".join(re.escape(t.capitalize()) for t in tokens) + r"\b",
                    r"\b" + re.escape(tokens[0].capitalize()) + r"\b"
                ]
                has_mixed = any(re.search(pat, full_text) for pat in mixed_patterns)
                if has_mixed:
                    discovered_entities[norm] = {
                        "name": caps_cand,
                        "confidence": 0.7,
                        "line": el.line_number,
                        "evidence": f"ALL-CAPS action intro '{caps_cand}' with mixed-case appearance",
                    }
                    existing_normalized.add(norm)
                    if len(discovered_entities) >= max_entities:
                        break

    # Build EntityDef models for candidates
    allocated_eids: Set[str] = set(graph.entities.keys())

    for norm, cand in sorted(discovered_entities.items(), key=lambda x: x[1]["name"]):
        name = cand["name"]
        raw_slug = slugify(name)
        candidate_eid = raw_slug
        suffix_counter = 2
        while candidate_eid in allocated_eids:
            candidate_eid = f"{raw_slug}_{suffix_counter}"
            suffix_counter += 1
        allocated_eids.add(candidate_eid)

        display_name = name.title()
        aliases = [name.upper()]
        words = name.split()
        if len(words) > 1:
            first_w = words[0].upper()
            if not any(first_w in ent.aliases for ent in graph.entities.values()):
                if first_w not in aliases:
                    aliases.append(first_w)

        base_st_id = state_id(candidate_eid, "base")
        base_state = StateDef(
            id=base_st_id,
            slug="base",
            label=f"Base {display_name}",
            order=0,
            canons=[canon],
            attributes={"origin": "auto"},
        )

        ent_def = EntityDef(
            schema_version=SCHEMA_VERSION,
            entity_id=candidate_eid,
            display_name=display_name,
            aliases=aliases,
            canons=[canon],
            base_state="base",
            states=[base_state],
            transforms=[],
            attributes={
                "origin": "auto",
                "provisional": True,
                "confidence": cand["confidence"],
                "first_seen_line": cand["line"],
                "evidence": cand["evidence"],
            },
        )

        ent_dict = ent_def.model_dump()
        res.new_entities.append(ent_dict)
        res.patch_ops.append({"op": "add_entity", "entity": ent_dict})

    return res


def apply_discovery(
    graph: StoryGraph, result: DiscoveryResult, author: str = "auto"
) -> StoryGraph:
    """Applies discovery patch operations atomically to produce an updated in-memory graph."""
    if not result.patch_ops:
        return graph
    return apply_patch(graph, result.patch_ops, author=author)


def persist_discovery(
    result: DiscoveryResult, graph: StoryGraph, dir_path: Optional[Path] = None
) -> List[Path]:
    """
    Writes auto-discovered entity definitions into config/graph/characters/auto/*.json.
    Returns list of written file paths.
    """
    out_dir = Path(dir_path) if dir_path is not None else DEFAULT_AUTO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    parent_dir = out_dir.parent

    written: List[Path] = []
    # Write newly created entities
    for ent_data in result.new_entities:
        eid = ent_data["entity_id"]
        # If already defined in parent characters/ dir, skip writing duplicate in auto/
        if (parent_dir / f"{eid}.json").exists():
            continue

        # Fetch current consolidated entity from graph if present
        if eid in graph.entities:
            ent = graph.entities[eid]
        else:
            ent = EntityDef.model_validate(ent_data)

        target_file = out_dir / f"{eid}.json"
        target_file.write_text(ent.model_dump_json(indent=2), encoding="utf-8")
        written.append(target_file)

    # Also update any auto entities that received new auto-discovered states
    entities_with_new_states = {s["entity"] for s in result.new_states}
    for eid in entities_with_new_states:
        if (parent_dir / f"{eid}.json").exists():
            continue
        if eid in graph.entities:
            target_file = out_dir / f"{eid}.json"
            target_file.write_text(graph.entities[eid].model_dump_json(indent=2), encoding="utf-8")
            if target_file not in written:
                written.append(target_file)

    return written
