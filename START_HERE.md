# Start and return to work

The current candidate is running at http://127.0.0.1:8795 while its process remains active. It opens `out/story_graph_authoring_20261102`, a separately copied saved snapshot containing ten timeline entries. DeepSeek is the selected provider; Venice is selectable as backup, and Gemini is available through the Antigravity session.

This new workspace does not include unsaved drafts or proposal/session history from earlier running editors. It does not replace those workspaces. Return to an earlier editor using its existing browser tab or URL, and save any draft there before closing it. Do not copy an old proposal history or recovery journal into this edition as a shortcut: the history is bound to its edition path and recovery journals may contain absolute paths.

To start the candidate later, open PowerShell and run the following from the project folder. If port 8795 is in use, choose another free port; do not stop an existing editor just to reuse it.

```powershell
Set-Location 'C:\Users\User\OneDrive\Current Work\Documents\ChatGPT\Local Stuff\SOL_HANDOFF_2026-11-01\projects\deepseek_narrative_composer'
python -m narrative_composer.editor --file out/story_graph_authoring_20261102/gemini_hot_scoomp_master.md --manifest out/story_graph_authoring_20261102/gemini_hot_scoomp_master.manifest.json --entity-dir out/story_graph_authoring_20261102/characters --canon hot_scoomp_main --port 8795
```

Open `http://127.0.0.1:8795`. Select an edition from the timeline; save unsaved text and formatting before switching. Select a character/form in the graph to inspect its port, character trace or appearances in the current text. An author-added form remains a provisional option until separately reviewed. Dataset attachment requires a compatible local package and pinned binding as described in [character data ports](CHARACTER_DATA_PORTS.md).

The editor starts with DeepSeek, but a selected provider's credentials and connectivity must be configured and tested separately. Model responses are proposals for review. If a proposal-history write fails, copy the visible response or retry saving it before closing the process. If the outcome of a request is uncertain, inspect proposal history and verify that no other editor is processing it before explicitly allowing a new request.

The [recovery record](RECOVERY_STATUS.md) contains current tests and limitations. Synthetic timeline exercise copies are labeled and are not author-approved story editions.

The 50% Peter Rainee form is an available, separately addressable option with provisional links; it is not treated as a source event. Use the Condition selected paragraph control for an action paragraph, or use Condition prose for flagged actions. Notes and dialogue are not supported by that conditioner path.
