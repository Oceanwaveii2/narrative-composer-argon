"""Tests for the live-preview editor helpers (server-independent)."""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.compiler.document import parse_document
from narrative_composer.editor import (
    apply_node_edit,
    block_info,
    build_editor_store,
    carry_dirty_edits,
    document_stats,
    node_payload,
    render_source,
    save_source,
    save_workspace,
    update_block_text,
)
from narrative_composer.graph.models import EntityDef
from narrative_composer.models.epistemic import NarrativeFact
from narrative_composer.store import entity_definition

ROOT = Path(__file__).resolve().parents[2]
SCREENPLAY = ROOT / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
MANIFEST = ROOT / "hot_scoomp_manifest.json"

SCRIPT = (
    "# ACT ONE\n\n## SCENE 1\n\nINT. OFFICE - DAY\n\n"
    "DANA stands at the window.\n\n**DANA:** \"Who is this?\"\n"
)


class TestEditorHelpers(unittest.TestCase):
    def test_render_source_produces_a_reader(self):
        rendered = render_source(SCRIPT)
        self.assertIn("<!DOCTYPE html>", rendered)
        self.assertIn('id="int-office-day"', rendered)
        self.assertIn("DANA", rendered)

    def test_document_stats(self):
        stats = document_stats(SCRIPT)
        self.assertGreaterEqual(stats["blocks"], 4)
        self.assertGreaterEqual(stats["scenes"], 1)
        self.assertGreater(stats["words"], 5)
        self.assertEqual(stats["characters"], len(SCRIPT))

    def test_save_source_keeps_a_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.md"
            path.write_text("original", encoding="utf-8")
            save_source(path, "updated")
            self.assertEqual(path.read_text(encoding="utf-8"), "updated")
            self.assertEqual(
                path.with_suffix(".md.bak").read_text(encoding="utf-8"), "original"
            )

    def test_block_info_reports_role_and_line(self):
        document = parse_document(SCRIPT)
        action = next(b for b in document.blocks if b.role.value == "action")
        info = block_info(SCRIPT, action.id)
        self.assertEqual(info["role"], "action")
        self.assertEqual(info["text"], action.text)
        self.assertGreaterEqual(info["line"], 1)

    def test_update_block_rewrites_its_source_line(self):
        document = parse_document(SCRIPT)
        action = next(b for b in document.blocks if b.role.value == "action")
        updated = update_block_text(SCRIPT, action.id, "DANA studies the empty street.")

        self.assertIn("DANA studies the empty street.", updated)
        self.assertNotIn("DANA stands at the window.", updated)
        # The rest of the document is untouched and still parses to the same shape.
        self.assertEqual(len(parse_document(updated).blocks), len(document.blocks))
        self.assertIn("**DANA:**", updated)

    def test_update_block_preserves_heading_markup(self):
        document = parse_document(SCRIPT)
        scene = next(b for b in document.blocks if b.role.value == "scene_heading")
        updated = update_block_text(SCRIPT, scene.id, "INT. OFFICE - NIGHT")
        self.assertIn("INT. OFFICE - NIGHT", updated)
        self.assertIn("## SCENE 1", updated)

    def test_update_block_rejects_multiline_and_unknown_ids(self):
        document = parse_document(SCRIPT)
        action = next(b for b in document.blocks if b.role.value == "action")
        with self.assertRaises(ValueError):
            update_block_text(SCRIPT, action.id, "two\nlines")
        with self.assertRaises(KeyError):
            update_block_text(SCRIPT, "no-such-block", "x")


class TestNodeBackedEditor(unittest.TestCase):
    """The editor's edits go through nodes, not raw string replacement."""

    @classmethod
    def setUpClass(cls):
        cls.source = SCREENPLAY.read_text(encoding="utf-8")

    def _store(self):
        return build_editor_store(self.source, SCREENPLAY, MANIFEST)

    def test_edit_block_node_returns_new_text(self):
        store = self._store()
        block = next(b for b in store.of_kind("block") if b.data["role"] == "action")
        updated = apply_node_edit(store, block.id, "An action line edited as a node.")

        self.assertIn("An action line edited as a node.", updated)
        self.assertEqual(len(updated.split("\n")), len(self.source.split("\n")))
        self.assertEqual(node_payload(store, block.id)["kind"], "block")

    def test_edit_state_node_marks_entity_dirty_and_projects_out(self):
        store = self._store()
        node_id = "st:stella.state.nerd_20"
        data = dict(store.node(node_id).data)
        data["label"] = "Dork transformation 20 percent"

        result = apply_node_edit(store, node_id, json.dumps(data))

        self.assertIsNone(result, "editing a state must not change the screenplay text")
        self.assertIn("stella", store.meta["dirty_entities"])
        labels = {s["label"] for s in entity_definition(store, "stella")["states"]}
        self.assertIn("Dork transformation 20 percent", labels)

    def test_dirty_entity_edits_survive_rebuild(self):
        first = self._store()
        node_id = "st:stella.state.nerd_20"
        data = dict(first.node(node_id).data)
        data["label"] = "Survives a rebuild"
        apply_node_edit(first, node_id, json.dumps(data))

        rebuilt = build_editor_store(
            self.source + "\n\nINT. NEW SCENE - DAY\n\nAn extra action line.\n",
            SCREENPLAY,
            MANIFEST,
        )
        carried = carry_dirty_edits(first, rebuilt)

        self.assertEqual(carried.node(node_id).data["label"], "Survives a rebuild")
        self.assertIn("stella", carried.meta["dirty_entities"])
        labels = {s["label"] for s in entity_definition(carried, "stella")["states"]}
        self.assertIn("Survives a rebuild", labels)

    def test_identity_fields_are_immutable(self):
        store = self._store()
        node_id = "st:stella.state.nerd_20"
        data = dict(store.node(node_id).data)
        data["id"] = "stella.state.hacked"
        with self.assertRaises(ValueError):
            apply_node_edit(store, node_id, json.dumps(data))

    def test_dirty_fact_node_survives_rebuild(self):
        first = self._store()
        node_id = "fact:fact_hg_pricing"
        data = dict(first.node(node_id).data)
        data["canonical_text"] = "Carried fact text."
        apply_node_edit(first, node_id, json.dumps(data))

        rebuilt = build_editor_store(
            self.source + "\n\nINT. X - DAY\n\nY.\n", SCREENPLAY, MANIFEST
        )
        carried = carry_dirty_edits(first, rebuilt)
        self.assertEqual(carried.node(node_id).data["canonical_text"], "Carried fact text.")

    def test_save_writes_manifest_back(self):
        store = self._store()
        node_id = "fact:fact_hg_pricing"
        data = dict(store.node(node_id).data)
        data["canonical_text"] = "Updated fact text from the editor."
        apply_node_edit(store, node_id, json.dumps(data))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            screenplay = tmp_path / "draft.md"
            screenplay.write_text(self.source, encoding="utf-8")
            entity_dir = tmp_path / "characters"
            entity_dir.mkdir()
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")

            saved = save_workspace(
                store,
                self.source,
                screenplay,
                entity_dir=entity_dir,
                nodes_out=None,
                manifest_path=manifest_path,
            )

            self.assertEqual(saved["manifest"], "manifest.json")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["facts"]["fact_hg_pricing"]["canonical_text"],
                "Updated fact text from the editor.",
            )
            NarrativeFact(**payload["facts"]["fact_hg_pricing"])
            self.assertTrue((tmp_path / "manifest.json.bak").exists())
            self.assertEqual(store.meta["dirty_nodes"], [])

    def test_save_preserves_manifest_formatting(self):
        store = self._store()
        node_id = "fact:fact_hg_pricing"
        data = dict(store.node(node_id).data)
        data["canonical_text"] = "Edited without reformatting the file."
        apply_node_edit(store, node_id, json.dumps(data))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            screenplay = tmp_path / "draft.md"
            screenplay.write_text(self.source, encoding="utf-8")
            entity_dir = tmp_path / "characters"
            entity_dir.mkdir()
            manifest_path = tmp_path / "manifest.json"
            original = json.loads(MANIFEST.read_text(encoding="utf-8"))
            manifest_path.write_text(
                json.dumps(original, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
            )

            saved = save_workspace(
                store,
                self.source,
                screenplay,
                entity_dir=entity_dir,
                nodes_out=None,
                manifest_path=manifest_path,
            )

            text = manifest_path.read_text(encoding="utf-8")
            self.assertEqual(saved["manifest"], "manifest.json")
            self.assertIn('\n    "manifest_name"', text, "4-space indentation must survive")
            self.assertEqual(text, json.dumps(json.loads(text), indent=4, ensure_ascii=False) + "\n")

    def test_save_writes_the_identity_sidecar(self):
        store = self._store()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            screenplay = tmp_path / "draft.md"
            screenplay.write_text(self.source, encoding="utf-8")
            entity_dir = tmp_path / "characters"
            entity_dir.mkdir()

            saved = save_workspace(
                store, self.source, screenplay, entity_dir=entity_dir, nodes_out=None
            )

            self.assertEqual(saved["ids"], "draft.md.ids.json")
            self.assertTrue((tmp_path / "draft.md.ids.json").exists())

    def test_manifest_is_not_rewritten_for_text_only_changes(self):
        store = self._store()
        block = next(b for b in store.of_kind("block") if b.data["role"] == "action")
        apply_node_edit(store, block.id, "A changed action line.")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            screenplay = tmp_path / "draft.md"
            screenplay.write_text(self.source, encoding="utf-8")
            entity_dir = tmp_path / "characters"
            entity_dir.mkdir()
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
            before = manifest_path.read_bytes()

            saved = save_workspace(
                store,
                self.source,
                screenplay,
                entity_dir=entity_dir,
                nodes_out=None,
                manifest_path=manifest_path,
            )

            self.assertIsNone(saved["manifest"])
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_save_workspace_projects_text_entity_and_nodes(self):
        store = self._store()
        node_id = "st:stella.state.nerd_20"
        data = dict(store.node(node_id).data)
        data["label"] = "Dork transformation 20 percent"
        apply_node_edit(store, node_id, json.dumps(data))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            screenplay = tmp_path / "draft.md"
            screenplay.write_text(self.source, encoding="utf-8")
            entity_dir = tmp_path / "characters"
            entity_dir.mkdir()
            nodes_out = tmp_path / "nodes.json"

            saved = save_workspace(
                store,
                self.source.replace("The sedan", "The car", 1),
                screenplay,
                entity_dir=entity_dir,
                nodes_out=nodes_out,
            )

            self.assertIn("stella.json", saved["entities"])
            written = json.loads((entity_dir / "stella.json").read_text(encoding="utf-8"))
            EntityDef.model_validate(written)
            self.assertIn(
                "Dork transformation 20 percent", {s["label"] for s in written["states"]}
            )
            self.assertIn("The car", screenplay.read_text(encoding="utf-8"))
            self.assertTrue(nodes_out.exists())
            self.assertEqual(store.meta["dirty_entities"], [])


if __name__ == "__main__":
    unittest.main()
