# Narrative Composer — getting started

Narrative Composer is an editing and review prototype for working with an existing story. It connects the text to per-character graphs, transformation states and optional data ports, then offers composer and prose-conditioner proposals for the author to review.

This private repository contains the available **American Foxy Momma / Hot Scoomp** timeline. The master and some component sections overlap; keep them separate. The Tapped Out materials include incomplete variants.

## Before you begin

- Get access to this private GitHub repository and install Git and Python **3.13 or newer**.
- This repository does not contain API keys, installed dependencies, or prior provider sessions.
- Preserve the supplied stories. Create a working copy before editing, composing, or saving. Do not censor or merge editions, and do not treat synthetic rules as canon.
- For Argon or another developer, read [ARGON_GITHUB_HANDOFF.md](ARGON_GITHUB_HANDOFF.md) and [PROGRAMMING_GUIDE.md](PROGRAMMING_GUIDE.md). The handoff's older launch command opens the supplied snapshot directly; follow the working-copy steps below instead. Some historical documents refer to paths or generated runs not included in this focused snapshot.

## 1. Clone and install

Clone the repository using an account that has access:

```powershell
git clone https://github.com/Oceanwaveii2/narrative-composer-argon.git
cd narrative-composer-argon
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If PowerShell blocks activation, use `./.venv/Scripts/python.exe` in place of `python` for the remaining commands. On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

## 2. Make a working copy

From the repository root, run:

```powershell
python -c "import shutil; shutil.copytree('out/story_graph_authoring_20261102', 'out/authoring_work')"
```

This copies the saved timeline, character definitions and associated data into `out/authoring_work`. The command stops if that destination already exists; choose a different name rather than overwrite an existing working copy. Use the same name in the launch command below. The supplied snapshot remains at `out/story_graph_authoring_20261102`.

## 3. Start the editor

```powershell
python -m narrative_composer.editor `
  --file out/authoring_work/gemini_hot_scoomp_master.md `
  --manifest out/authoring_work/gemini_hot_scoomp_master.manifest.json `
  --entity-dir out/authoring_work/characters `
  --canon hot_scoomp_main --port 8795
```

The backticks above are PowerShell line continuations. On macOS or Linux, use the same command on one line or use shell-appropriate continuations.

Open [http://127.0.0.1:8795](http://127.0.0.1:8795). If that port is in use, choose a free port in the command and URL. The editor binds locally.

Use the timeline selector to open an edition, then open the character graph and select a character or form to inspect its source trace and data port. A form can be available without being observed in an edition. Full behavioral profiles are optional and have not been invented for this project.

## 4. Providers and review

- **DeepSeek** is the default. Configure `DEEPSEEK_API_KEY` in your environment before using it.
- **Venice** is a manually selectable backup; configure `VENICE_API_KEY` in your environment.
- **Gemini · session** uses the signed-in Antigravity CLI (`agy`) and does not require a Gemini API key in this app. Select it in the editor or start the editor with `--provider gemini_session`.

No credentials are included in the repository. Keep keys out of Git, issue reports, and chat logs. The app does not silently switch providers when a request fails.

Use the composer and conditioner on the chosen edition and supported passage. Inspect each proposal against the original and its graph context, then explicitly accept or reject it. A passing mechanical check is not proof that meaning or voice was preserved. The selected-paragraph conditioner supports action paragraphs; notes and dialogue are not supported by that path. If a request fails or a passage is unsupported, leave the source intact and record the limitation.

Gemini conditioning has returned intermittent empty responses in live neutral tests; a later successful retry did not establish reliability. See [RECOVERY_STATUS.md](RECOVERY_STATUS.md) for the current evidence and limits.

## 5. Verify the installation

From the repository root:

```powershell
python reproductions/check_bugs.py
python -m unittest discover -s narrative_composer/tests -t .
```

The focused snapshot was checked with 6/6 reproduction checks and 405 Python tests run, with 16 skipped. The editor, ten-entry timeline and Rainee trace were also opened in a disposable copy. Browser tests are separate: install the frontend dependencies and a Playwright Chromium browser, then run `npm run test:e2e` from `frontend`.

## Where things are

- `out/story_graph_authoring_20261102/timeline.json` — inventory of the ten available timeline entries.
- `out/story_graph_authoring_20261102/sources/` — supplied chronology and Tapped Out source documents.
- `out/story_graph_authoring_20261102/characters/` — character and form definitions for the timeline.
- [CHARACTER_DATA_PORTS.md](CHARACTER_DATA_PORTS.md) — data-port behavior and provenance.
- [FUTURE_CHARACTER_DATA_BOUNDARY.md](FUTURE_CHARACTER_DATA_BOUNDARY.md) — deferred Super JSON / Deep Character integration.
- [RECOVERY_STATUS.md](RECOVERY_STATUS.md) — verified behavior and outstanding limitations.

Keep each edition and incomplete variant separate. Do not replay historical recovery journals or assume a copied proposal database or provider session belongs to a new checkout.
