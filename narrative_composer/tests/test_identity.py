"""Tests for stable block identity across edits (sidecar map)."""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.identity import (
    entries_from_document,
    load_entries,
    save_entries,
    sidecar_path,
    stabilize,
)

SCRIPT = """INT. ROOM - DAY

A lamp glows.

A lamp glows.

**DANA:** "Hello."
"""


class TestIdentity(unittest.TestCase):
    def test_editing_a_block_keeps_its_id(self):
        first = parse_document(SCRIPT)
        entries = entries_from_document(first)
        target = next(b for b in first.blocks if b.role.value == "action")
        old_id = target.id

        edited = SCRIPT.replace(target.text, target.text + " (revised)")
        second = parse_document(edited)
        stretch = stabilize(second, entries)

        revised = next(b for b in second.blocks if b.text.endswith("(revised)"))
        self.assertEqual(revised.id, old_id, "an edited block must keep its identity")
        self.assertIn(old_id, {entry["id"] for entry in stretch})

    def test_inserting_a_duplicate_keeps_original_ids(self):
        first = parse_document(SCRIPT)
        entries = entries_from_document(first)
        original_ids = [b.id for b in first.blocks if b.text == "A lamp glows."]
        self.assertEqual(len(original_ids), 2)

        # Insert another identical line above the first one.
        inserted = SCRIPT.replace("A lamp glows.", "A lamp glows.\n\nA lamp glows.", 1)
        second = parse_document(inserted)
        stabilize(second, entries)

        surviving = {b.id for b in second.blocks if b.text == "A lamp glows."}
        for block_id in original_ids:
            self.assertIn(block_id, surviving, "duplicate IDs must not be renumbered")

    def test_new_blocks_get_fresh_ids(self):
        first = parse_document(SCRIPT)
        entries = entries_from_document(first)
        old_ids = {entry["id"] for entry in entries}

        appended = SCRIPT + '\nINT. NEW ROOM - DAY\n\nA brand new action.\n'
        second = parse_document(appended)
        stabilize(second, entries)

        new_block = next(b for b in second.blocks if b.text == "A brand new action.")
        self.assertNotIn(new_block.id, old_ids)

    def test_duplicate_sidecar_ids_are_reissued(self):
        """A sidecar written before ID uniqueness can contain duplicate IDs; never reuse one."""
        first = parse_document(SCRIPT)
        entries = entries_from_document(first)
        entries[0]["id"] = entries[1]["id"] = "poisoned-id"

        second = parse_document(SCRIPT)
        stabilize(second, entries)

        ids = [block.id for block in second.blocks]
        self.assertEqual(len(ids), len(set(ids)), "block IDs must remain unique")
        self.assertEqual(ids.count("poisoned-id"), 1)

    def test_sidecar_round_trips(self):
        document = parse_document(SCRIPT)
        entries = entries_from_document(document)
        with tempfile.TemporaryDirectory() as tmp:
            path = sidecar_path(Path(tmp) / "draft.md")
            save_entries(path, entries)
            loaded = load_entries(path)
        self.assertEqual(loaded, entries)

    def test_missing_sidecar_returns_none(self):
        self.assertIsNone(load_entries(Path("does-not-exist.ids.json")))

    def test_corrupt_sidecar_is_a_visible_conflict(self):
        from narrative_composer.compiler.identity import IdentitySidecarError
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md.ids.json"
            path.write_text("}{ not json", encoding="utf-8")
            with self.assertRaises(IdentitySidecarError):
                load_entries(path)
            path.write_text('[{"id":"one","role":"action","text":"ok"},{"id":"incomplete"}]', encoding="utf-8")
            with self.assertRaises(IdentitySidecarError):
                load_entries(path)


if __name__ == "__main__":
    unittest.main()
