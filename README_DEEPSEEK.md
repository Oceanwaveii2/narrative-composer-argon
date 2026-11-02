# Neurosymbolic Narrative Node Graph (NNG) — DeepSeek System Guide

A narrative analysis, editing, and generation prototype with character-state graphs and prose tools. The November 1 review found unresolved integration and data-integrity defects; passing component tests or a DOM audit does not establish reliable fiction or preserved meaning.

> **RECOVERY IN PROGRESS.** The user explicitly resumed coding and testing. The existing character graphs and their data ports come first, followed by integration and exercises across the available Episode 0 through Tapped Out material. The system is not yet qualified end to end.
>
> **Recovery authority for this copy:** [Integration-first recovery and programming guide](PROGRAMMING_GUIDE.md). Required order: integration and authored-work integrity → full viewport review → narrative authoring and character-recomputation exercises. Candidate implementation and some checks were performed after “do all” was interpreted as resume; complete integration and qualification remain unverified. See [recovery status](RECOVERY_STATUS.md) and [Tapped Out source map](TAPPED_OUT_CORPUS_MAP.md). Historical handoff checksums predate these edits.

---

## 1. What This System Does

When large language models generate or rewrite multi-act stories, they often suffer from:
1. **State Drop & Reversion Hallucinations**: Forgetting a character's current physical form (e.g. treating Stella as normal fox when she is in Big Tiddy Steve form, or forgetting Francine's nurse uniform).
2. **Illegal State Jumps**: Skipping necessary intermediate physical steps (e.g. jumping straight from standard to extreme form without trigger events).
3. **Multiverse / Canon Leaks**: Accidentally bringing in characters or cues from alternative universes (a cue whose only entity is scoped to a canon the scene does not belong to).
4. **Contradictory Visual Anchors**: Describing clothing or body traits that belong to another state.

The current prototype attempts to detect a subset of these issues through graph extraction and checks. The recovery guide documents where inference, validation, and state ownership must be separated:
- **Symbolic Layer (Configured Definitions)**: Formal directed graphs of entities, states, transforms, visual anchors, and descriptive trigger metadata. Discovered/inferred states are not automatically approved ground truth.
- **Narrative AST Parser**: Ingests screenplay text, extracts speaker cues and action descriptions, and maps them to chronological state instances.
- **Invariant Checker**: Flags configured continuity issues and unresolved evidence. The extractor also reports unverified events and stale state reviews (G8 and G10) as errors, and reviewed states with unverified causes (G9) as warnings. Inspect each report for its actual severity and coverage.
- **Interactive Visualizer**: Generates a zero-CDN, self-contained HTML node graph matching the Character Story Graph blueprint.

---

## 2. Directory Structure

```text
deepseek_narrative_composer/
├── HOT_SCOOMP_COMPLETE_CHRONOLOGY.md   # One story compilation; user says corpus is incomplete
├── hot_scoomp_manifest.json            # Epistemic facts, spatial rooms/props, causal DAG
├── run_pipeline.py                     # One-click runner script
├── README_DEEPSEEK.md                  # This instruction manual
├── PROGRAMMING_GUIDE.md                # Recovery order, integration contracts, pause and acceptance gates
├── narrative_composer/                 # Core Python package
│   ├── cli.py                          # CLI interface (--graph-build, --manifest, --status)
│   ├── config/graph/                   # Canonical character definitions & rules
│   │   ├── characters/                 # stella.json, rainee.json, francine.json, haley.json, etc.
│   │   ├── world.json                  # World relationship/fact seed data
│   │   └── triggers/                   # Trigger and cue dictionaries (descriptive metadata only)
│   ├── graph/                          # Graph models, AST extractor, verifier, & visualizer
│   │   ├── models.py                   # Pydantic schemas (EntityDef, StateDef, TransformDef)
│   │   ├── resolver.py                 # Canon-aware speaker cue and alias resolver
│   │   ├── extract.py                  # Screenplay AST -> Chronological State Instances
│   │   ├── checks.py                   # Invariant verifier (illegal transitions, leaks, anchors)
│   │   ├── viewer.py                   # Zero-CDN interactive Character Story Graph visualizer
│   │   └── pipeline.py                 # Full pipeline orchestration
│   ├── models/                         # Epistemic matrix, spatial FSM, causal DAG
│   ├── parser/                         # Screenplay Fountain/Markdown AST lexer
│   └── tests/                          # Component/regression tests; see recovery evidence limits
└── out/graphs/                         # Generated execution artifacts
    ├── master.graph.json               # Full graph data, state instances, timeline
    ├── master.chain.json               # Cooked operator network (node DAG + params), not per-character chains
    ├── master.report.json              # Detected violations, suggestions, and summary
    └── master.viewer.html              # Standalone interactive Character Story Graph
```

---

## 3. How to Run the System

### A. One-Click Pipeline Execution
Run the full screenplay through the graph engine:
```bash
python run_pipeline.py
```
This parses `HOT_SCOOMP_COMPLETE_CHRONOLOGY.md`, checks configured graph constraints and writes graph outputs to `out/graphs/`. Unmodeled events and pending causes are not automatically verified.

### B. Standard CLI Execution
You can also run via the package CLI directly:
```bash
python -m narrative_composer.cli --graph-build HOT_SCOOMP_COMPLETE_CHRONOLOGY.md --canon hot_scoomp_main --run-id master --no-learn
```

### C. Running Unit Tests
Run the test suite from the project root. Results and remaining skips are recorded in the recovery status:
```bash
python -m unittest discover -s narrative_composer/tests -t .
```

### D. Inspecting Manifest & Causal DAG
Check prop inventories, room topologies, and causal DAG beat prerequisites:
```bash
python -m narrative_composer.cli --manifest hot_scoomp_manifest.json --status
```

### E. Tiptap document editor and graph
Edit the screenplay in the document surface with a source-based reader or graph beside it:
```bash
python -m narrative_composer.editor --file HOT_SCOOMP_COMPLETE_CHRONOLOGY.md --port 8765
```
Then open <http://127.0.0.1:8765>. The left pane is a Tiptap editor; the right pane is a source-based reader or the character graph. `Ctrl/Cmd+S` saves. By default the server binds to loopback; do not bind it to a public interface without adding the necessary protections.

To open the prepared Episode 0 through Tapped Out workspace in PowerShell, run:

```powershell
python -m narrative_composer.editor `
  --file out/recovery_execution_20261101_bb463e69/workbench/gemini_hot_scoomp_master.md `
  --manifest out/recovery_execution_20261101_bb463e69/workbench/gemini_hot_scoomp_master.manifest.json `
  --entity-dir out/recovery_execution_20261101_bb463e69/workbench/characters `
  --canon hot_scoomp_main --port 8785
```

Open <http://127.0.0.1:8785> if that recovery server is already running; otherwise run the command above, choosing another unused port if needed. The separate workbench starts with a byte-verified copy of the Gemini chronology plus nine recovery sections. The Tapped Out outline extractions and the later Quick Story are separate variants requiring review; they are not automatically merged. The selector prevents a switch while the current section has unsaved changes. Unsaved work in an older editor session is not present in this copy; preserve it in that session. Use one editor session per working edition.

To add another Word variant without replacing an existing edition, use a new lowercase ID:

```powershell
python -m narrative_composer.corpus --workspace out/american_foxy_timeline_recovery `
  --variant-docx 'C:/path/to/source.docx' --variant-id a_new_variant
```

The original is copied alongside a plain-text projection and a paragraph/run record; review the projection against the original Word formatting. Adding a variant does not approve its events as canon.

The editor supports text, bold, italic, underline, paragraph style and alignment.
Existing Fountain/Markdown syntax stays visible. **Character graph** includes a character/forms view with individual data ports;
**Nodes & diagnostics** exposes editable nodes and source-form observations. See
[character data ports](CHARACTER_DATA_PORTS.md) for port modes and review behavior.

Save validates the draft, detects external edits, and uses a recovery journal for related
files, including a `<story>.md.rich.json` formatting sidecar that must accompany the story.
Text and formatting undo are paused while structured graph or beat changes are unsaved.
The **Formatted document (.html)** export includes the editor's visual styles; the `.md`
export is the text projection and does not encode new sidecar formatting. See [document
engine status and recovery notes](DOCUMENT_ENGINE_STATUS.md) for format and conflict limits.

The **Repair proposals** button proposes fixes for individual targets — deterministic surgical patches
for tier-1 rules, model rewrites for tier-2 rules — and shows each as original → proposed.
Applying a reviewed proposal changes the draft; saving is a separate action. Review the target and meaning before applying. **DeepSeek** is the editor's default writing provider; **Venice** is the backup selected in the provider menu or with `--provider venice`. No provider is switched automatically after a failure or refusal. **DeepSeek session** keeps a per-edition local conversation history; **Codex session** remains optional. Inference is online. `mock` is an offline placeholder. The standalone CLI remains mock by default; explicitly use `--mode deepseek` or `--mode venice` for those providers. The selected remote provider receives the target and its relevant story context.

For new writing, **New beat** lets the author enter a scene heading, optional characters and a dramatic goal without changing the document. **Draft selected beat** proposes a selected actionable beat; review and apply it before saving. The nine recovery section manifests have no authored beats until the user adds them. The separate Gemini master manifest has six existing beats with incomplete flags; these flags have not been reconciled to its already-written story.

The reader is fully self-contained — the Tailwind runtime is vendored and inlined, and the
font stack falls back locally — so both the reader and the preview work offline.

### F. Unified Node Store
Project text, character definitions, the manifest and diagnostics into one node graph:
```bash
python -m narrative_composer.store build --out out/nodes.json
python -m narrative_composer.store diagnose out/nodes.json
python -m narrative_composer.store export-entity out/nodes.json stella --out out/stella.json
```
Every block, scene, entity, state, transform, fact, prop and beat is a node with an ID;
edges connect them (`has_block`, `speaks_as`, `realizes`, `has_state`, `reaches`,
`depends_on`). Both checkers report into a single diagnostic stream addressed by node ID,
and `to_text()` / `entity_definition()` project the store back to screenplay text and
character JSON. Targeted checks cover block identity, inline editing, full model projection
and edited-state diagnostics. They do not establish complete source-format or semantic
fidelity; see the recovery status for actual evidence and limits.

### G. Ingesting a New Story
Adapt a prose-style script, auto-discover its cast, and render a standalone reader:
```bash
python -m narrative_composer.story \
  --file stories/rainee_realm/source.md \
  --cast stories/rainee_realm/cast.json \
  --out out/rainee_realm \
  --title "Realm of Space-Time - Episode 1" \
  --canon rainee_realm
```
The intake copies the source bytes without silently normalizing or conditioning them. It
discovers candidate characters, optionally uses bilingual aliases from `--cast`, and writes
a new project with `story.md`, `manifest.json`, character definitions, `nodes.json`,
`report.json`, and `reader.html`. Discovered character data and an empty world manifest
are starting points for review; they are not verified canon or Deep Character datasets.

### H. Prose Conditioning (review-first)
```bash
python -m narrative_composer.condition --file out/rainee_realm/story.md \
  --out out/rainee_realm/conditioned_review --provider codex --limit 1
```
Finds the action paragraphs that prose diagnostics flag (sensory deficit, monotonous
cadence, observer filters), asks the model to rewrite only that paragraph, then validates
each candidate mechanically: invariant gate, length ratio 0.5–2.2, and no new filter words or
emotion labels. An explicit `--manifest` supplies prop and knowledge context. These checks
do not establish preserved meaning. A length or subject/action failure may receive one bounded retry. Venice can be selected explicitly with `--provider venice`. Review `proposals.json` and `review.html` first. To
apply reviewed block IDs, run again with a **new** output folder, `--apply --proposals
<review-folder>/proposals.json --approve <block-id>`. The second run uses the saved
candidate, not a fresh model response; it validates the source hash and writes a separate
conditioned copy only for explicitly approved blocks. Existing output artifacts are not
overwritten.

---

## 4. How DeepSeek Should Use the Graph to Avoid Errors

When generating story continuations, rewrites, or analyzing scenes, DeepSeek should adhere to the following **System Instructions**:

### Guardrail 1: Query Current State Before Writing
Before writing dialogue or action, inspect the selected story section's character graph and its evidence. A form is attached to its actor's path and has its own ID and data port. The definitions include Stella's 20%, 40%, 70%, legacy 80% and Steve forms, plus Rainee's individually identified celebrity forms and Peter form. Steve is Stella's own Steve-like persona and retains Stella's memories. See [character data ports](CHARACTER_DATA_PORTS.md) for supported behavior and current limitations.

For generated pipeline reports, `master.graph.json` contains state instances; `master.chain.json` is an operator network, not a character timeline. A state inferred from a cue or starting-state selection is not automatically an author-approved fact.

### Guardrail 2: Do Not Jump States Without Trigger Events
When a scene requires a transition, review the observed state, permitted direct transition, and evidence of its cause. The current extractor can check configured trigger events or patterns where supplied; its pattern matching is not general causal understanding. An unverified event is reported instead of silently making a multi-step transition authoritative. Accepting a state observation still leaves its cause pending review.

### Guardrail 3: Respect Detected Report Violations
The verifier reports continuity problems in `master.report.json`; the current extractor can also report G8 and G10 as errors and G9 as a warning. Inspect the actual report for severity, source evidence and unmodeled coverage.
- Historical reports contained a `G3_CANON_LEAK` for `MA MA LING`; commit `70332d4` added `hot_scoomp_main` to her configured canons. The November 1 audit run reported zero graph errors/warnings, within the limitations in `PROGRAMMING_GUIDE.md`. Future configuration changes require an author-approved canon decision, not an edit made solely to silence a report.
- **Do not invent model edges to silence a report.** The former `G1_ILLEGAL_TRANSITION` at line 2352 was a false positive: the `nerd_20` entry pattern matched the word "polo" inside a description of the costume Stella was still wearing as `big_tiddy_steve`. Adding a reverse transform — as earlier drafts of this guide suggested — would have taught the graph a transition the story never contains. Fix the extraction pattern, not the canon.

---

## 5. Viewing the Interactive Graph

Open `out/graphs/master.viewer.html` directly in any web browser (Chrome, Edge, Firefox).
- **Features**:
  - Top tab bar ranking all characters by instance count.
  - Purple Character Root Node with character goals.
  - Sequentially numbered spine event nodes linked with white arrows.
  - Blue Knowledge nodes (`📖`) showing visual anchors and extracted state cues.
  - Red Consequence nodes (`❗`) showing exact lines where continuity rules were violated.
  - Green Outcome nodes (`🏆`) marking the climax resolution state.
  - Zero CDN dependencies (100% offline, self-contained SVG & CSS).
