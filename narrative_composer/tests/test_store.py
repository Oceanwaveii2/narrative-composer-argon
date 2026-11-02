"""
Tests for the unified node store: one graph for text, story state, and diagnostics.
"""

import tempfile
import unittest
from pathlib import Path

from narrative_composer.compiler.document import parse_document
from narrative_composer.graph.models import EntityDef
from narrative_composer.store import (
    NodeStore,
    build_store,
    entity_definition,
    set_block_text,
    summary,
    to_text,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"


class TestNodeStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_bytes().decode('utf-8')
        cls.store = build_store()

    def test_projects_all_four_sources_into_one_graph(self):
        kinds = summary(self.store)["kinds"]
        for kind in ("block", "scene", "entity", "state", "transform", "fact", "prop", "beat"):
            self.assertIn(kind, kinds, f"missing {kind} nodes")
            self.assertGreater(kinds[kind], 0)

    def test_text_projection_is_lossless(self):
        self.assertEqual(to_text(self.store), self.source)

    def test_text_nodes_attach_to_story_nodes(self):
        speaks_as = [e for e in self.store.edges if e.type == "speaks_as"]
        realizes = [e for e in self.store.edges if e.type == "realizes"]
        self.assertTrue(speaks_as, "cue blocks should connect to entities")
        self.assertTrue(realizes, "blocks should realize character states")
        self.assertTrue(all(edge.src.startswith("blk:") for edge in speaks_as))
        self.assertTrue(all(edge.dst.startswith(("ent:", "st:")) for edge in realizes))

    def test_entity_projection_validates_as_the_real_schema(self):
        for entity_id in ("stella", "rainee", "francine"):
            payload = entity_definition(self.store, entity_id)
            definition = EntityDef.model_validate(payload)
            self.assertEqual(definition.entity_id, entity_id)
            self.assertTrue(definition.states)

    def test_editing_a_node_changes_exactly_one_line(self):
        store = NodeStore.from_dict(self.store.to_dict())
        block = next(b for b in store.of_kind("block") if b.data["role"] == "action")
        set_block_text(store, block.id, "A rewritten action line from the node store.")

        before = self.source.split("\n")
        after = to_text(store).split("\n")
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(after), len(before))
        self.assertEqual(len(changed), 1)
        self.assertIn("A rewritten action line", after[changed[0]])

    def test_diagnostics_are_one_stream_addressed_to_nodes(self):
        diagnostics = self.store.meta.get("diagnostics", [])
        self.assertTrue(diagnostics)
        sources = {d["source"] for d in diagnostics}
        self.assertEqual(sources, {"graph"})
        self.assertTrue(
            all(d["node_id"] for d in diagnostics),
            "every diagnostic must point at a node",
        )

    def test_registry_from_store_reflects_in_session_edits(self):
        """Editing an entity in the store must change diagnostics without saving."""
        import re

        from narrative_composer.store import registry_from_store

        store = NodeStore.from_dict(self.store.to_dict())
        unresolved = [
            d for d in store.meta["diagnostics"] if d["rule_id"] == "G6_UNRESOLVED_CUE"
        ]
        self.assertTrue(unresolved)
        cue = None
        for diagnostic in unresolved:
            match = re.search(r"Unresolved speaker cue '([^']+)'", diagnostic["message"])
            if match and re.fullmatch(r"[A-Z][A-Z0-9 .'-]+", match.group(1)):
                cue = match.group(1)
                break
        self.assertIsNotNone(cue, "expected at least one plain unresolved cue")

        entity = store.node("ent:stella")
        data = dict(entity.data)
        data["aliases"] = list(data.get("aliases", [])) + [cue]
        entity.data = data
        store.meta["dirty_nodes"] = [entity.id]

        registry = registry_from_store(store)
        rebuilt = build_store(registry=registry)
        remaining = [
            d
            for d in rebuilt.meta["diagnostics"]
            if d["rule_id"] == "G6_UNRESOLVED_CUE" and cue in d["message"]
        ]
        self.assertEqual(remaining, [], f"'{cue}' should resolve after adding the alias")

    def test_manifest_nodes_hold_full_model_data(self):
        beat = self.store.node("beat:cold_open").data
        self.assertIn("dramatic_goal", beat)
        self.assertIn("active_characters", beat)
        prop = self.store.node("prop:gloria_lamp").data
        self.assertIn("equipped_slot", prop)

    def test_manifest_payload_round_trips_manifest(self):
        import json

        from narrative_composer.store import manifest_payload

        manifest = json.loads((ROOT / "hot_scoomp_manifest.json").read_text(encoding="utf-8"))
        payload = manifest_payload(self.store, manifest)
        self.assertEqual(sorted(payload), sorted(manifest))
        self.assertEqual(
            payload["facts"]["fact_hg_pricing"]["canonical_text"],
            manifest["facts"]["fact_hg_pricing"]["canonical_text"],
        )
        self.assertEqual(
            payload["beats"]["cold_open"]["dramatic_goal"],
            manifest["beats"]["cold_open"]["dramatic_goal"],
        )

    def test_build_cache_returns_independent_copies(self):
        from narrative_composer.store import clear_build_cache

        clear_build_cache()
        first = build_store()
        second = build_store()
        first.node("ent:stella").data["display_name"] = "MUTATED"
        self.assertEqual(second.node("ent:stella").data["display_name"], "Stella")
        self.assertEqual(build_store().node("ent:stella").data["display_name"], "Stella")

    def test_cache_is_keyed_on_text(self):
        from narrative_composer.store import clear_build_cache

        clear_build_cache()
        first = build_store()
        second = build_store(
            text=self.source + "\n\nINT. EXTRA - DAY\n\nAn extra action.\n"
        )
        self.assertGreater(len(second.nodes), len(first.nodes))

    def test_build_honours_the_identity_sidecar(self):
        import tempfile

        from narrative_composer.compiler.identity import save_entries, sidecar_path
        from narrative_composer.compiler.identity import IdentitySidecarError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(self.source, encoding="utf-8")

            first = build_store(script_path=path, text=self.source, use_cache=False)
            block = next(b for b in first.of_kind("block") if b.data["role"] == "action")
            old_id, old_text = block.id, block.data["text"]
            save_entries(sidecar_path(path), first.meta["id_map"])

            edited = self.source.replace(old_text, old_text + " (edited)", 1)
            path.write_text(edited, encoding="utf-8")
            with self.assertRaises(IdentitySidecarError):
                build_store(script_path=path, text=edited, use_cache=False)
            second = build_store(script_path=path, text=edited, use_cache=False,
                                 allow_unverified_identity_reconciliation=True)

            matches = [
                b for b in second.of_kind("block") if b.data["text"] == old_text + " (edited)"
            ]
            self.assertTrue(matches, "edited block should exist")
            self.assertEqual(matches[0].id, old_id, "sidecar must preserve identity across edits")

    def test_store_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.store.save(Path(tmp) / "nodes.json")
            reloaded = NodeStore.load(path)
        self.assertEqual(len(reloaded.nodes), len(self.store.nodes))
        self.assertEqual(len(reloaded.edges), len(self.store.edges))
        self.assertEqual(to_text(reloaded), self.source)
        self.assertEqual(
            reloaded.node("ent:stella").data["display_name"],
            self.store.node("ent:stella").data["display_name"],
        )

    def test_document_block_ids_are_the_store_ids(self):
        """The store must not invent a second identity space."""
        document = parse_document(self.source)
        for block in document.blocks[:50]:
            self.assertIn(f"blk:{block.id}", self.store.nodes)


if __name__ == "__main__":
    unittest.main()
