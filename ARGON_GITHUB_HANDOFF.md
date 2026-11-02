# Narrative Composer: Argon handoff

This GitHub repository is a focused, unencrypted snapshot of the application and the available American Foxy Momma / Hot Scoomp timeline. It includes the source code, editor assets, tests, relevant guides, original chronology, and the current ten-entry timeline with its source documents and separate incomplete variants. Older generated runs, unrelated sample stories, dependencies and local credentials were excluded. Historical guides may reference outputs that are not included or say that credentials were present in an earlier handoff; no credentials are included here.

Preserve the author's story files. Do not edit, delete, censor, merge, or silently replace original editions. Work on a separate copy and keep generated changes as reviewable proposals. Do not invent behavioral profiles or treat synthetic fixtures as canon.

The current timeline is out/story_graph_authoring_20261102/ and its timeline.json. The master and its component sections overlap and should not be concatenated. The 50% Peter Rainee state is available, not necessarily observed. Character graphs are source-linked paths with independently addressable form data ports; full behavioral profiles are optional.

Read PROGRAMMING_GUIDE.md, RECOVERY_STATUS.md, CHARACTER_DATA_PORTS.md, and FUTURE_CHARACTER_DATA_BOUNDARY.md. Existing absolute paths in historical metadata refer to the original machine. Do not replay old recovery journals or assume old provider sessions or saved proposal databases are valid in this checkout.

From the repository root, with Python 3.13 or newer:

    python -m pip install -e .
    python -m narrative_composer.editor --file out/story_graph_authoring_20261102/gemini_hot_scoomp_master.md --manifest out/story_graph_authoring_20261102/gemini_hot_scoomp_master.manifest.json --entity-dir out/story_graph_authoring_20261102/characters --canon hot_scoomp_main --port 8795

Open http://127.0.0.1:8795. Choose another port if needed. Install frontend dependencies with npm ci inside frontend to rebuild or run browser tests. Configure provider credentials or Gemini Antigravity sign-in on the new machine.

Suggested checks:

    python reproductions/check_bugs.py
    python -m unittest discover -s narrative_composer/tests -t .

The live Gemini conditioner has shown intermittent empty responses; a successful neutral retry did not establish reliability. Report failed or unsupported stages and retain the exact originals for review.

Focused snapshot checks: 6/6 reproduction checks passed; 405 Python tests ran with 16 skipped and no failures. The editor, ten-entry timeline and Rainee trace opened in a disposable copy.
