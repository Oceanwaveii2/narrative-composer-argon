# Narrative Composer — integration-first recovery and programming guide

## Story-first graph correction

The primary current workflow uses the author's existing text and evidence. A full behavior/personality model is optional and must not be a prerequisite for tracing characters, editing their forms, making a bounded proposal or reviewing a source-linked inconsistency. The `rainee.state.peter_50` form is an author-defined, separately addressable option with provisional connections; it is not an observed scene. Preserve legacy IDs and the direct Peter path. See [character data ports](CHARACTER_DATA_PORTS.md) and the [future data boundary](FUTURE_CHARACTER_DATA_BOUNDARY.md).

Character traces distinguish cue-linked dialogue, lexical action mentions and lexical outline-note mentions. None establishes motives, action ownership or an approved transition by itself. Form views distinguish graph instances, source observations, and no detected appearance. Unverified G2/G8 observations are displayed as author-review questions, while their underlying gate remains active for newly introduced unresolved states. Never downgrade the gate merely to make a displayed count smaller.

An unverified pattern-detected event with no defined path is an unverified observation, not an author-asserted illegal transition. Do not issue an additional G1 merely because that candidate lacks a path; retain G8 and the review gate. Explicit illegal transition checks still apply to truly asserted transitions. Convergence must stay pending when review questions or unmodeled graph coverage remain, even if the display has zero technical errors.

The composer receives a bounded, provenance-labeled sample of existing source text for active characters when available; that material is untrusted source data, not instructions or an approved personality. Proposals retain source revision, validation results and relevant graph links. An author can select one action paragraph for conditioning even if automatic diagnostics did not flag it; unsupported notes/dialogue must remain explicit rather than silently converted. The key-omission sentinel is a narrow regression guard, not proof that ownership or other semantic facts survived a rewrite.

An Antigravity CLI result may report `SUCCESS` while its response is empty and no answer event was emitted. Do not accept that as a completed proposal or overwrite the previous conversation; expose the failed turn without switching providers. Keep the empty-success regression case alongside incomplete-timeout and completed-result-after-shutdown cases. The observed cause and live reliability remain unresolved.

## Release-candidate operating rules and evidence

The [start guide](START_HERE.md) identifies the current candidate, its separate edition workspace, how to launch it, and how to return to earlier sessions. The [recovery record](RECOVERY_STATUS.md) and [viewport/document review](output/playwright/viewport_document_review_20261101/RECOVERY_AND_VIEWPORT_REVIEW.md) distinguish verified fixture behavior from unqualified capabilities. A running editor retains the code it loaded at startup: never call an old process the current build. Preserve any unsaved drafts before closing it.

The core ownership chain is: **edition source and identity map → document/store → graph definitions and edition-scoped observations → revision-bound composer or conditioner proposal → explicit author decision → journaled story, rich-formatting and identity commit**. Character definitions and their datasets are shared within a workspace; manifests, source text, source indexes and proposal history must retain the selected edition's identity. A diagnostic or a lexical mention is evidence to review, not approval of a state transition, personality, causal event or generated claim. The author owns acceptance; model output and mechanical checks cannot grant it.

### Regression cases that must remain covered

| Boundary or previous failure | Required check before qualification |
|---|---|
| Source and projection | Run `python reproductions/check_bugs.py`; verify non-cue prose and sound effects, duplicate IDs, one node per block and lossless projection. Compare original input hashes before and after exercises. Never replace a damaged identity map silently; use [identity recovery](IDENTITY_RECOVERY.md). |
| Character and form ports | Check each actor/state ID and parent edge; test inherited, empty replacement, domain override, owner mismatch, missing/hash-changed package, and an unrelated character's cache. Recheck edition filename, source hash, block/line hashes and timeline label. A `resolved` source-index connection is not authored behavioral data. |
| Observation and transition | A cue, state marker or `state_event` can report evidence but cannot authorize its own cause. Filter obvious non-speaker warnings only after resolving configured aliases; do not change parser identities or source-index links as a side effect. Verify the form-appearance view opens the correct edition's source block. |
| Proposal and model request | Require a captured source, graph/data and rich-formatting revision, explicit decision and fresh validation at apply time. A delayed result is stored as stale, never applied to newer work. An identical request ID replays a completed saved result; pending or uncertain requests must not silently run again. Different IDs or legacy clients without IDs are not deduplicated automatically. |
| Failed proposal history | Commit a request's complete proposal batch and replay record together. Test write failure, no partial batch, retry, restart and replay. An unsaved proposal remains visible only while its process lives: tell the author to copy it or retry before closing. |
| Save and recovery | Exercise formatting and text together, undo/redo, explicit accept/reject, stale revision, external edits, interrupted journal recovery and cross-process conflicts. A failed operation must leave the last saved artifacts intact; do not replay copied absolute-path journals. Local locks do not coordinate other machines or arbitrary editors. |
| Viewport and accessibility | At each target size exercise the long document, graph, data port, proposal comparison and error state. Modal errors must appear in the dialog with an alert; controls and dialogs need meaningful accessible names. Keyboard-only, real IME, screen reader, native scaling and print preview are separate acceptance checks, not implied by a screenshot. |
| Document formats | Verify source/identity/rich-sidecar hashes and actual save/reload. HTML is a view export; Word direct-run import is limited and DOCX/PDF layout round trips are not implemented. Headless print rendering is not native print-preview or a complete pagination review. |

### Current qualification boundary

The integration exercises and browser checks are offline and use disposable fixtures; ten timeline cases used synthetic Stella rules and mock writing. Eight mock conditioner candidates were held by checks; two outline editions contain no action blocks and were not conditioned. The master still has 161 cue/state mismatch findings and 17 unverified events requiring review. Seven actors lack authored behavior-rule packages; the two legacy profiles are unreviewed. Do not describe these results as approved canon, a full-story rewrite, model quality validation or a complete psychological simulator.

The 1280×800, 1600×1000 and 1920×1080 browser views and one emulated 1.5 device-pixel ratio have been inspected. Native IME, screen-reader operation, native print preview, broad native scaling, and complete DOCX/PDF round trips remain unqualified. The reader iframe's `allow-scripts` plus `allow-same-origin` warning also requires a separate security review. Do not suppress these gaps with aggregate pass counts.

## Current recovery control

Follow the concrete [system recovery plan](SYSTEM_RECOVERY_PLAN.md) and its gates before claiming completion. The [latest system evaluation](out/system_evaluation_20261101_01/EVALUATION.md) records the observed recurring failure pattern. This work is authorized to proceed, with original sources and alternate editions preserved.

**Prevent repeat failures:** keep pending proposals across replanning, timeline switches and restarts; reject corrupt identity sidecars visibly; avoid overwriting output artifacts; serialize cross-process writes and release the save lock during provider calls. Make form-port selection authoritative for embedded and packaged data, and label lexical evidence, unreviewed profiles, missing behavior and unresolved causes separately. Every provider path returns a revision-bound proposal, not a silent edit. Check the real caller, resulting artifact, failure path and author-facing status together—not a component or test count in isolation.

Integrate and protect authored work first, then perform the full viewport review, then the narrative authoring and recomputation exercises. Record evidence against the precise build and edition. Historical results do not validate later untested changes.

### Mandatory execution protocol

1. **Name the invariant before editing.** Record the observed failure, the author-visible behavior that must be preserved, the affected edition/workspace, the actual producer and consumer, and a reproducible neutral case. Trace the complete path before adding a local workaround.
2. **Protect all authored artifacts, not only the story file.** This includes formatting and identity sidecars, character data, proposed writing, review decisions, output documents and recovery journals. Existing invalid sidecars or journals are conflicts; a missing file and a damaged file are not interchangeable. A new output uses an unoccupied, verified destination.

   Legacy identity sidecars are lists without source hashes. On opening an existing sidecar, its recorded role/text/line entries must match the source exactly; a partial map or external text change is a visible recovery conflict, not permission to generate replacement IDs. In-session editing still reconciles the previous map and saves a new one with the draft.
3. **Give each piece of state one owner.** Source text, rich formatting, block identity, graph definitions, source observations, profile/rule packages, world facts, proposals and accepted events have different lifetimes. The contracts and owning files are in the [recovery plan](SYSTEM_RECOVERY_PLAN.md#ownership-contracts). Every cross-boundary operation names its base revision and edition.
4. **Keep model work outside save ownership.** Capture an immutable revision and data inputs, allow independent saving/navigation during a slow request, and persist a late answer as stale instead of applying it to newer work. Provider failures, partial responses, retries and history conflicts must remain visible and recoverable.
5. **Apply form data consistently.** Resolve actor and form bindings by domain once. Empty `replace` cannot fall back to embedded actor rules or profiles; `override` replaces only explicitly named domains. A loaded source index is evidence of a connection, not a personality model or a reaction engine.
6. **Separate evidence from authority.** Candidate cast, lexical mentions, inferred cues, hypothetical forms, unreviewed profiles, reviewed observations, approved causes, proposals and accepted edits are distinct. Review an observation and its transition cause separately; never add a cause, personality or fact merely to eliminate a diagnostic.
7. **Verify at the real boundary.** Test from the author-facing caller through downstream state, persistence and reload, including adversarial failure cases. Use process barriers/fault injection for concurrency, not only successful helper calls. A model API response, a graph picture, a unit-test count or a DOM audit is evidence only for that specific check.
8. **Keep the stage report honest.** Record `passed`, `failed`, `not run`, `not modeled`, `pending review`, `stale` or `blocked` for analysis, reactions, composition, conditioning, review, save and viewport. Show missing character data and incomplete editions; zero findings in an unmodeled domain is not verification.
9. **Record changes as candidates until qualified.** Identify which server process is running which build, which checks ran after the latest change, and any partial or conflicting work. Update the issue register and evidence; do not reset a dirty checkout or discard an earlier workspace to create a cleaner-looking result.
10. **Use the author's review where it is genuinely necessary.** Ask for missing character datasets, ambiguous story facts or acceptance decisions; continue independent engineering work without inventing those answers. Preserve each partial Tapped Out variant and the author's explicit exclusions and planned-but-unwritten events.

### Minimum completion evidence

The [acceptance matrix](SYSTEM_RECOVERY_PLAN.md#acceptance-matrix) is the baseline for sign-off, and the [original-findings crosswalk](SYSTEM_RECOVERY_PLAN.md#crosswalk-to-the-original-22-findings) assigns a current regression check to each audit item. For every resolved issue, record its trigger, source/edition and build, expected versus observed behavior, test or visual evidence, any skipped checks, and whether a human decision is still pending. Integration and authored-work integrity precede the full-window review; the authoring and recomputation exercises follow that review. A valid test on an old editor process does not qualify a later source change.

Updated November 1, 2026. Governs recovery in this reviewed handoff copy; does not designate this copy as the owning checkout of the wider Noir product.

## Authorization and status

**EXECUTION RESUMED.** The user explicitly said “Resume coding and testing” and requested the existing character graphs and data ports first, followed by authoring and recomputation exercises across the available Episode 0 through Tapped Out timeline. Earlier candidate work and checks preceded that explicit resume after “do all” was interpreted as authorization. The text-editor/output-formatting requirement remains part of integration. Follow [current recovery status](RECOVERY_STATUS.md) for evidence and limits.

The user confirmed this is the Narrative Composer guide. Full viewport review concerns its integrated editor, graph, reader, diagnostics, and proposal surfaces. The subsequent exercises concern narrative authoring and character recomputation. No drawing engine or work in another drawing app is in scope.

The user requested an editable document engine and graphic layouts. A first Tiptap editor is now integrated with the existing text/graph/proposal paths; its verified behavior and limits are in [document engine status](DOCUMENT_ENGINE_STATUS.md). The wider [document engine and Graphite layout plan](DOCUMENT_ENGINE_AND_GRAPHITE_PLAN.md) includes work not yet implemented or qualified.

The editor defaults to **DeepSeek** as the main provider. **Venice** is the manually selected backup. **Gemini · session** uses the signed-in Antigravity CLI, not a Gemini API key; Codex remains optional. Providers are never switched automatically after a refusal or failure. The standalone CLI remains offline/mock by default and accepts an explicit `--mode deepseek` or `--mode venice`. The user authors or explicitly selects beat goals before generation. Do not turn model suggestions, form observations, synthetic test rules, incomplete variants or missing character data into accepted canon. A selected model receives the applicable manuscript excerpt and context; identify that scope when testing or documenting the workflow.

One conditioner rejection arose when its prompt encouraged added detail without stating its own length gate; another treated the sentence starter “Together” as a missing proper name. Prompt constraints and bounded retries must agree with the validator, and subject checks must not mistake common sentence starters for names. A separate composer failure occurred when a selected form's cue was absent from the generation prompt: provide the form ID and configured cue, while retaining graph validation. Passing a mechanical gate means eligible for review, not semantically correct. Check source hashes before and after timeline exercises and never replay copied recovery journals that contain absolute original paths.

The research agent completed read-only research; its recommendations are incorporated here. Current implementation, viewport, and exercise evidence is tracked separately in `RECOVERY_STATUS.md`. Previous audit results remain historical evidence.

Evidence: [audit and findings F01–F22](<C:/Users/User/.codex/visualizations/2026/11/02/01a19a0f-cb3a-7863-99c0-1ce0aae956b7/narrative-composer-review/REVIEW.md>). Code baseline reviewed: `6bb671af7bf01dbb8d2780b9af37aa99f56ca313`, with pre-existing chronology edits, `.tmp/`, and untracked reproductions. Preserve these originals and changes. Historical handoff checksums predate the present guide edits and are not a refreshed inventory.

## Required order and outcome

Recover one coherent workflow:

**Intake → reviewed character/world definitions → character computation → composition → rewrite proposals → validation → author decision → recoverable save/reload.**

After explicit resume, integration comes first, then the full viewport review, then narrative authoring exercises. Focused checks belong within integration work; the later exercises qualify the assembled author workflow. Visual polish, publishing expansion, and additional character features wait for these gates. Reuse sound components instead of starting another general rewrite.

## Audit baseline versus recovery target

The left column describes the historical audit baseline, not necessarily the current recovery build. Some target behaviors are now partially implemented; use [recovery status](RECOVERY_STATUS.md) for verified results and remaining gaps.

| Area | Audited baseline | Recovery target; partially implemented |
|---|---|---|
| Main runner | Graph extraction/checks, prose metrics, reader, DOM audit. | Explicit orchestration and truthful completion status for the selected integrated workflow. It currently does not call the beat composer or model-based conditioner. |
| Intake | Format adaptation, cast discovery, baseline states, empty world manifest. | Reviewed modeling and visible coverage/unknowns. Zero errors cannot imply unmodeled knowledge, props, or causality were verified. |
| Character models | `EntityDef` continuity data and separate `DialecticCharacterNode` prompt profiles. | One authoritative actor identity linking versioned continuity, personality, memory/world references, and evaluator inputs. |
| Procedural network | Eight shared operators; hidden character context can evade invalidation. | Explicit versioned dependencies and scoped character recomputation. |
| Changes | Separate conditioner, recook, composer, and editor paths with different gates. | One revision-aware proposal, validation, author-decision, and commit contract. |
| Store/editor | Combined graph/diagnostics with incomplete projections and saves. | Exact spans/IDs, full models, fresh diagnostics, and recoverable revisions. |

Do not call graph display or richer JSON an implemented reaction simulator. Separate deterministic computation, recorded replay, and fresh stochastic/external generation. Fresh model output is not promised to be deterministic.

## Integration contracts to establish before implementation

### C1 — One accepted project revision

Specify a project snapshot containing or referencing authored source/hash, persistent document/block identity and exact source spans, approved character/world definitions, personality/evaluator versions, accepted events, evidence locators, proposal decisions, schema versions, and dependency identities.

Every render, diagnostic result, character computation, proposal, and saved artifact names the same base revision. Persistent identity is separate from a content hash. An edit invalidates results without renaming the author's object. Preview rendering must not independently allocate IDs that differ from the editor/store. Identify the authoritative manifest/profile locations rather than maintaining competing active copies.

### C2 — Three graphs with distinct authority

| Graph | Owns | Required boundary |
|---|---|---|
| Approved definition graph | Character forms, permitted transitions, rules, reviewed configuration. | Discovery cannot approve new legality. |
| Story event/evidence graph | Observed events, asserted cues, evidence, inferred hypotheses, accepted history. | A cue or inferred path cannot prove its own causal event. |
| Executable dependency graph | Operators and complete versioned inputs/outputs. | No result-affecting hidden mutable context outside fingerprints. |

Joined views do not erase these authority boundaries. Shared worlds and relationships remain referenced outside an actor definition. Character substitution must not silently rewrite shared world facts.

### C3 — Character evaluator and recomputation boundary

Define inputs: actor/instance identity, personality/function version, accepted state, scoped knowledge, perceived events, relevant relationships/world context, rules, and generation/replay policy. Define outputs: reaction/action candidates, proposed deltas, reasons/evidence, uncertainty, and dependency identities. Evaluation proposes; it does not directly commit canon.

Replacing a character package names the affected scope/revision and invalidates dependent results. Preserve unaffected facts and identity. Downstream event changes require review before acceptance. Record new model results; replay refers to their recorded identities and provenance.

### C4 — One proposal and commit path

Map runner, intake, editor, composer, conditioner, selective recook, and batch recook to stages of the same workflow. Diagnostic-only commands may remain separate but must report omitted stages.

Every proposed change records base revision, target IDs/spans, original content/hash, candidate content, protected spans/preserved claims, knowledge and prop scope, required causal events, provider/evaluator provenance, validation results, and review state. Nonempty output and transport success are not acceptance. Semantic uncertainty remains pending review.

Validate beat beliefs/props/events before generation and before commit. Revalidate the assembled candidate, not just individual paragraphs. Accepted changes advance a revision through one commit boundary. Rejected/stale changes leave accepted work unchanged. Every change path must use this gate; a new command cannot implement a weaker bypass.

### C5 — Strict storage and safe persistence

Reject duplicate insertion, missing endpoints, invalid identities, unresolved required references, and cyclic/incomplete execution. Intentional replacement uses explicit update operations. Preserve complete versioned schema payloads, including deprecated status, voice, future personality fields, and provenance.

Represent an inline source line once with addressable children/spans. Preserve offsets, formatting, and unrelated content. Prepare and validate every projected artifact before publishing a recoverable revision. Design recovery across the complete save; independent `.bak` files do not establish transaction safety. Detect external edits and serialize conflicting commits. Non-writing modes remain non-writing for every iteration.

### C6 — Truthful status and coverage

Use **passed, failed, not run, not modeled, pending review, stale, blocked** as applicable. A required-check exception cannot become zero errors. An empty manifest cannot establish continuity. Valid DOM cannot establish good prose or preserved meaning. Inferred evidence stays labeled. A single source of truth is a target until round-trip/dependency behavior is demonstrated across real entry points.

## Recovery work packages and remaining qualifications

| Order | Concrete deliverable and owning areas | Findings | Required future exit evidence |
|---|---|---|---|
| I0 — Integration map | Identify owning checkout, orchestrator, authoritative files, entry points, model owners, bypasses, and minimal scenario. | Architectural root causes; F21 | Producer→consumer matrix shows authority and revision at every handoff. No competing owner remains unresolved. |
| I1 — Author-work integrity within the slice | Parser/document spans, projections, IDs, full models, graph insertion, edited-state rebuild, persistence. | F07–F09, F11–F14, F18–F20; duplicate-ID boundary | Inline edits survive; deprecated fields stay deprecated; scene links exist; preview/store IDs agree; diagnostics use edited data; rejected/non-writing operations preserve accepted files. |
| I2 — Character/event integration | Extraction, approved definitions, discovery proposals, evaluator dependencies, oriented paths, multi-entity events, beat/world preconditions, provenance. | F03–F06, F10, F15–F16, F21 | No self-authorizing cue/discovery; changed character inputs invalidate affected outputs; all events on a line remain; evidence identities/bounds are authoritative. |
| I3 — Shared rewrite/commit gate | Conditioner, recook, composer, revision/decision records, assembled validation, overall status. | F01–F02, F06, F17, F22 | Contradictory rewrites rejected/pending; invariants run on every change path; skipped/failed stages visible; save/reload preserves accepted meaning and identity. |
| V — Full viewport review | Integrated editor, graph, reader, inspectors, diagnostics, review, navigation, save/conflict/status. | Integration presentation/usability | Full-window evidence identifies actual build, project revision, viewport, behavior, limitations, and reviewer decision. |
| E — Narrative authoring exercises | Perform the scenarios below against that same integrated revision. | Workflow qualification | Expected/observed behavior and evidence for every exercise; open issues explicitly tracked. |

I0–I3 form the first milestone: one representative integrated vertical slice. A component fix alone cannot close an integration issue. Exercise its real caller and downstream consumer, including save/reload where relevant. Some candidate evidence exists; use the recovery status for what has actually been checked.

## Full viewport review — partially exercised

Headless Chrome has been checked at three viewport sizes against a timeline sandbox, including the Tiptap document surface and graph. Graph inspection, source-form review, save/reload, editing and exports were exercised; print preview, native scaling, accessibility and IME remain open. See [recovery status](RECOVERY_STATUS.md) for the exact evidence. The future graphical layout surface requires its own review when built.

After integration, inspect the actual application at user-agreed window sizes and scaling. Record viewport, display scaling, source/build revision, document revision, route, and active data. Review the full window before isolated controls. Mark unavailable surfaces not reviewed; do not bypass access restrictions.

Inspect editor/reader identity agreement, all-character and selected-character graphs, navigation, inspectors, diagnostic scope/severity, proposal differences/decisions, saved/unsaved state, and pending/stale/failure states. Include long/bilingual text, large graphs, empty or unmodeled input, provider failure, unsupported transitions, invalid edits, and save conflicts.

Check legibility, clipping, scrolling, focus, selection continuity, and visibility of warnings/unknowns. Record observed behavior alongside full-window evidence. Cropped panels and mockups do not qualify the viewport; screenshots alone do not qualify the engine. Return discovered integration failures to their owning contract before focused re-review.

## Narrative exercises

The available Episode 0 through Tapped Out material is the primary exercise corpus; isolated checks already performed are recorded in [recovery status](RECOVERY_STATUS.md). A supplementary neutral fixture is proposed: Dana and Alex, one secret, one prop lifecycle, one causally triggered form change, and two distinct personality profiles. This is a scenario specification, not an existing approved manuscript. Record expected outcomes before execution.

| Exercise | Author action | Acceptance outcome |
|---|---|---|
| E1 — Intake/coverage | Import fixture; review entities and evidence; model secret/prop/rules. | Text and offsets preserved; unknown entities/unmodeled domains visible; no silent invented facts. |
| E2 — Editing/identity | Edit inline cue/dialogue, insert/reorder text, change metadata, inspect all views. | Stable identity, correct spans, no lost edits, full schema round-trip, same revision across views. |
| E3 — Causality/discovery | Assert unsupported changed-form cue; supply approved cause; introduce unknown form. | Unsupported assertions visible; hypotheses cannot authorize themselves; approved cause explains transition. |
| E4 — Character replacement | Replace Dana's personality/functions, retaining Alex and accepted world. | Fresh affected computations with reasons; unrelated facts/identity preserved; downstream changes proposed for review. |
| E5 — Prose meaning | Offer rewrite reversing locks/opens or stays/leaves. | Scope/checks visible; changed meaning rejected or pending review; no automatic semantic-success claim. |
| E6 — Knowledge/props | Generate/repair around unrevealed secret and destroyed prop through each production path. | No gate bypass; preconditions checked; rejected output cannot mutate accepted state. |
| E7 — Save/conflict/reload | Attempt invalid mixed save, stale proposal, external-edit conflict; accept valid revision and reload. | Failure preserves work; conflicts explicit; accepted text, IDs, models, decisions, diagnostics survive reload. |
| E8 — Language/completion | Use supported bilingual input; encounter missing provider, skipped check, incomplete beat graph. | Language limits and not-run/not-modeled/failed states visible; no false convergence/completion. |

These qualify narrative authoring and recomputation. No drawing-app exercises are implied.

## Mandatory programming rules

### Authored corpus and alternate drafts

The user clarified that **Tapped Out rewrite is the Stella → Big Tiddy Steve storyline**, not an additional episode. Several partial versions explore Stella becoming Steve and how and why Haley transformed her. These excerpts do not constitute the full story. Episode 0, Spring Break/Peter-Rainee, and the Hot Scoomp/Stella material provide a partial integration corpus; filenames containing `COMPLETE` do not override this author clarification. The supplied Tapped Out outlines and the later Quick Story Word variant, the user's account, source hashes, variant-specific events and graph requirements are mapped in [Tapped Out source and integration map](TAPPED_OUT_CORPUS_MAP.md).

Assign each source edition a separate identity, original file/hash, and explicit partial status. Keep version order separate from story chronology. Do not concatenate alternate versions into consecutive events, combine conflicting motivations, invent connective scenes, or count an absent ending as a parsing failure. Cross-edition comparison may propose differences for review; it cannot silently merge canon. Record the source edition and evidence span for every extracted event and transformation cause. A character/form ID can remain shared across editions while accepted event history and causality remain edition-scoped.

For the Stella exercise, inspect each available version independently for the transformation, Haley's involvement, and any stated motive. Report each as explicit evidence, hypothesis, contradiction, or absent from the excerpt. Missing evidence means unknown; a form label alone cannot establish cause or personality change.

The author's later correction establishes that this particular transformation does change Stella's active persona and behavior: she becomes her own version of Steve while retaining Stella's memories and actor identity. Represent this as an actual transformed form/persona, not just a costume or a label. Other forms may share or change personality according to their own authored data; do not generalize either assumption. The Steve form inherits Stella's source-evidence package in the rebuilt workspace; its form-specific behavioral data remains absent until real data is supplied.

For the author's intended continuation, Steve asks Hayley to stop Francine; sometime after Jess, Francine outsmarts Hayley and traps her in the basement. This is a planned event and has not yet been implemented or written as a scene. Keep unspecified sequencing and resolution open. The author excludes the breast-milk storyline from this version, including main-outline beat 11A and related material. Preserve the original source as evidence but do not promote that storyline into active scenes, summaries, proposals or exports. See the corpus map for source-specific details and the future acceptance exercises.

1. Name the user-visible invariant and real execution path before modifying a component. Inspect upstream producer and downstream consumer first.
2. Change the owning contract and its callers together. New entry points use the shared validation path.
3. Keep approved rules, observations/hypotheses, proposals, and accepted runtime state distinct.
4. Declare all cached-result dependencies and invalidation scope. Explain replay separately from new generation.
5. Preserve complete models and versions. Unsupported fields/statuses cannot silently disappear or reset.
6. Fail at graph/storage boundaries. A caller patch does not excuse permissive overwrite/drop behavior.
7. Compute diagnostics from the actual edited revision. Copying dirty nodes over already-checked data is insufficient.
8. Establish failure-safe editing/save behavior before expanding features. Backups alone do not prove transaction safety.
9. After resume, check real integration boundaries with adversarial cases. A manually fabricated intermediate cannot substitute for detecting a defect through the production path.
10. Use fixed fixtures independent of the mutable manuscript and pre-existing output. Introduce a second supported story format early.
11. Distinguish executed evidence from plans. Test counts, no crashes, DOM validity, transport success, semantic fidelity, and literary quality are separate claims.
12. Keep changes reviewable. Record why replacing a component is necessary and which behavior must survive.
13. The hold applies to delegated work and automatic verification. Research recommendations cannot authorize execution.
14. Required failed/stale/unrun checks prevent an unqualified completion claim. Record limitations and reviewer decisions.

## Evidence and next handoff

Each future package records issue/contract ID, trigger, expected behavior, owning revision/entry point, changed scope, checks actually executed, observed output, evidence, limitations, reviewer decision, and next dependency. Link evidence instead of copying stale totals into many guides.

**Current state:** the user explicitly resumed coding and testing. See `RECOVERY_STATUS.md`; do not infer completion from this specification.
