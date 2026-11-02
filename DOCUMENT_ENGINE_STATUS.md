# Tiptap document engine — implementation and limits

November 1, 2026. The recovery workspace now has a locally bundled Tiptap 3.32.2 editor. This is an integrated first implementation, not qualification of every document format or the planned Graphite layout bridge.

## Use it

Start the workspace from the project root:

```powershell
python -m narrative_composer.editor `
  --file out/recovery_execution_20261101_bb463e69/workbench/gemini_hot_scoomp_master.md `
  --manifest out/recovery_execution_20261101_bb463e69/workbench/gemini_hot_scoomp_master.manifest.json `
  --entity-dir out/recovery_execution_20261101_bb463e69/workbench/characters `
  --canon hot_scoomp_main --port 8785
```

Open `http://127.0.0.1:8785` if the recovery server is already running; otherwise use the command above, selecting another unused port if needed. Select a timeline section and edit directly in the left pane. The right pane shows the source-based reader or the character graph. Bold, italic, underline, visual paragraph styles, alignment, undo and redo operate in the document. Existing Fountain/Markdown syntax remains visible in the editor; paragraph style is visual and does not change the graph's interpretation of the text.

Use one editor window/server per working edition at a time; simultaneous editing sessions have not been fully qualified. The new workbench is a separate copy and cannot include unsaved changes from older editor sessions. Preserve those changes in their original session.

**Writing:** choose a timeline section, select **New beat**, enter the scene heading and your dramatic goal, and optionally select characters. Adding the beat changes only the unsaved plan and selects it. **Draft selected beat** shows a proposal for review. Apply a reviewed candidate to the unsaved document, then **Save draft** when ready. The nine recovery section manifests start with no authored beats; the Gemini master manifest has six existing beats whose completion flags do not establish whether corresponding material was already written. Review them before selecting one. The simple beat form creates independent beats in sequence; dependencies and detailed world state still require structured editing and review.

Without a launch option, the editor defaults to **DeepSeek · primary**. Select **Venice · backup** in the provider menu or start with `--provider venice` when you want Venice. The editor does not automatically switch services after a refusal or failure. DeepSeek uses a locally persisted, per-edition conversation and online inference. Open **Codex session** if you choose to use the continuing Codex App Server thread with `gpt-6.1-terra` at `max`; it remains an optional provider. **Mock** is offline placeholder prose. Conditioning requests at most one flagged paragraph by default for Codex (two for other providers) and may retry an eligible failure once. Model output remains pending until reviewed. The standalone CLI keeps an offline/mock default and accepts explicit provider options.

OpenAI describes the thread/turn/resume protocol in its [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server) and distinguishes it from one-off execution in [Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform). The local CLI version is experimental; compatibility and account access should be checked after upgrades.

The chosen remote provider receives the text and context needed for its request. In chat, **No additional story context** sends the user's message; **Current document + character graph** also sends the current section's text, manifest, graph definitions, detected states and resolved bound character records. The continuing thread retains context from earlier turns and sections. Conditioning sends a flagged paragraph and applicable manifest context; composition sends the beat goal, relevant modeled context and up to the last ten nonempty lines of the document. Chat replies can be added to the unsaved draft after review, but that manual insertion is not the same as the composer's automated checks. Choose a provider with this scope in mind.

For the Quick Story Word projection, directly recorded bold and italic runs are imported when all extraction spans still match. Other Word formatting and pagination require comparison with the original. The original DOCX remains separate.

Select **Formatted document (.html)** to export the current visual formatting as a self-contained HTML view. **Story text (.md)** exports the text projection; new visual formatting is stored in the sidecar, not encoded into that Markdown export. The source reader likewise renders the story text and its existing Markdown/Fountain syntax rather than the sidecar's visual styles.

## How saves and proposals work

- The text projection continues to feed the existing parser, graph, character computation, composer and conditioner. A versioned `<story>.md.rich.json` sidecar stores Tiptap paragraph IDs, visual styles and marks plus a hash of the exact source bytes. Keep the sidecar with the story to retain rich formatting. Tiptap line IDs and the graph's screenplay-block IDs are distinct; the current connection is the shared text projection and store revision, not a finished block-lineage mapping.
- Save validates that the rich document projects to the same text and writes the story, rich sidecar and other changed workspace artifacts through the existing recovery journal. The journal retains previous bytes; multi-file filesystem writes are recoverable, not one atomic filesystem operation. Unknown nodes, marks, duplicate IDs, external changes and stale sidecars cause a visible refusal rather than silent normalization.
- Repair, conditioning and composition produce pending proposals. Preview compares against the graph/store revision and rich-document fingerprint, and acceptance checks them again. A repair that crosses mixed styles or would replace multiple existing paragraphs is refused for manual editing; a uniform style is retained for the replacement. An accepted text repair is a Tiptap transaction and can be undone/redone. Composition appends without trimming the existing source.
- A composed beat also changes structured manifest state. Undo is paused while such a beat or other structured graph edits are unsaved; saving commits the combined revision and resets that session's undo history. Normal text and formatting undo remain available otherwise.
- If the story is edited outside the rich editor after a sidecar exists, loading reports a conflict. Preserve copies of the story, sidecar and `.revisions` directory for recovery; there is no automatic merge UI yet. The legacy source-only save path refuses to overwrite a story with a rich sidecar.

## Current boundaries

- Direct formatting supports bold, italic, underline and visual paragraph style/alignment. Clipboard content is pasted as plain text with a warning when rich formatting was present. Tables, images, complex document fields and graphical page layout are not supported in the editor.
- Graphite integration, paginated PDF, DOCX export, collaboration, split/merge lineage and complete keyboard/IME/accessibility and native-display qualification remain open. The HTML export is a rendered view, not a round-trip import format.
- The graph still contains unreviewed observations and continuity findings. Character data fixtures demonstrate wiring, not the missing Deep Character model. Model output remains subject to author review; mechanical checks cannot prove preserved meaning.
- In an isolated timeline audit, Terra Max produced seven mechanically eligible proposals from seven short pre-reviewed action passages, and Venice produced five eligible proposals and two held by a subject heuristic. The two outline-only sections had no selected action passage. None was applied. These results are not a full-story or literary-quality test; see [recovery status](RECOVERY_STATUS.md). The browser exercise used the offline mock provider.
- Build assets locally with `cd frontend; npm install; npm run build`. The checked-in bundle runs without a CDN. `npm run test:e2e` exercises the local editor in an isolated fixture with Chrome; its executable path can be supplied through `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Bundled dependency licenses are in `narrative_composer/assets/THIRD_PARTY_NOTICES.md`.
