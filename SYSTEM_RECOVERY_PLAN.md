# Narrative Composer recovery plan

November 1, 2026. The author requested a concrete plan, an updated programming guide, research, and fixes. This plan starts from the [system evaluation](out/system_evaluation_20261101_01/EVALUATION.md). A checked box is an acceptance gate, not a claim that the work is already done; record actual results in the recovery status.

## Objective and boundaries

Provide one reliable workflow for an authored edition: text and formatting → source-linked actor/form graph and explicitly connected character data → hypothetical or authored beat proposal → prose proposal → visible checks and author decision → recoverable save/reload. Keep the original source and alternate editions separate. The owner decides character data, state observations, transition causes, story changes and proposal acceptance; generated data and discovered cues are never automatically canon.

Work in this order: **integration and authored-work integrity; full viewport review; narrative authoring and character-recomputation exercises**. Focused tests belong inside each integration step. Do not describe a synthetic fixture, display graph, successful API call, or mechanical validator as a qualified character simulator or meaning-preserving manuscript rewrite.

## Why work was repeatedly redone

The recurring pattern is an integration and authority gap: individual features produced plausible results without sharing a durable, versioned contract for the author's text, graph inputs, model proposals and decisions. Examples include a form cue being used to validate its own transition, a character-data change not invalidating a cached result, a rewrite passing checks that lacked the relevant world facts, and a save or recook touching a different artifact than the author expected. A green component test could therefore coexist with lost edits, stale calculations or an incomplete end-to-end workflow.

The remedy is to establish ownership and preservation first, trace each change from its actual caller to its saved result, and prove failure behavior as well as the happy path. Keep independent editions, unreviewed evidence, missing data and generated suggestions visible instead of converting them into approved story facts. The issue register assigns the work; the historical crosswalk and acceptance matrix prevent an old failure from disappearing behind a new feature or test count.

## I0 — Preserve and identify the working material

- Record the selected source paths, hashes, edition identity, project revision and graph/profile versions. Keep the dirty checkout, original source files, old output folders, existing running editors and credentials intact.
- A new candidate or review artifact uses a new destination. Never replay a copied journal whose recorded targets refer to another workspace.
- **Gate:** source hashes match before/after non-writing exercises; failed, stale or interrupted operations cannot change authored content. Claims name precisely which files were checked.

## I1 — Editing, proposals and recovery

- Preserve generated proposals with their edition, source revision, target IDs, original/candidate text, provider, validation and decision state. A new planning request, timeline switch, restart or a second editor must not silently discard them. Show stale proposals and require a fresh validation before application.
- A missing identity sidecar can initialize a new map; an existing corrupt, malformed or partial sidecar must raise a recoverable, visible conflict and must not be replaced silently. Preserve duplicates only according to an explicit, tested migration rule.
- Use recoverable commits with interprocess coordination and conflict checks. Keep slow provider calls outside the save critical section; a later result must remain tied to its starting revision and cannot overwrite intervening edits.
- Commands that generate readers, reports or graphs must use a fresh output or visibly refuse an existing target. Non-writing manuscript mode must not imply outputs cannot overwrite other authored work.
- **Gate:** neutral fixtures demonstrate proposal retrieval after replanning, timeline switching and restart; malformed sidecars cause no writes; two processes cannot silently replace each other's saved session or workspace revision; slow generation does not block an independent save; stale results remain reviewable but cannot be applied to a changed draft.

## I2 — Character graphs and data ports

- Keep one actor identity and uniquely identified form/data-port nodes. Support `inherit`, `extend`, `override` and `replace` consistently across graph display, loaded packages, reaction evaluation and composer inputs. An empty replacement must not silently fall back to embedded actor behavior.
- Keep source references edition-scoped and hash-pinned. Lexical matches are candidates, not verified claims. Expose unreviewed discovered characters and missing datasets; do not pretend that the seven configured actors cover every detected speaker.
- Preserve profile ownership, aliases and review state. Do not fabricate missing personalities, rules, motivations, causal transformations or Super JSON data. Form-specific data can differ or be shared only when the author supplies it.
- **Gate:** a form-specific replacement affects that actor's proposed reaction and required downstream work, unrelated data remains intact, bad/mismatched/stale inputs are visible, and a new cue cannot authorize its own transition. Review the 178 master findings by cause; do not silence them by inventing edges.

## I3 — One proposal and provider contract

- The composer, conditioner and recook must carry a common base revision, original target, provider/model, checks and review status; generated text is a proposal. Applying a reviewed candidate revalidates it against the actual current text, formatting, graph and world state.
- A mechanical pass is not a semantic approval. Present the original and proposed content together, including missing/changed facts and uncertainties where detectable. Never silently change model providers or apply a model's refusal, truncated response or empty output as prose.
- Use DeepSeek as the main editor provider and Venice as the manually selected backup. Verify the DeepSeek session through the documented API with per-edition context and explicit local history; protect secrets and simultaneous writers. Verify the Venice path separately. Test live providers only with independently reviewed, appropriate material and isolated neutral fixtures; no full mixed-content story is automatically sent for generation.
- **Gate:** offline transport tests cover errors, truncation, replay, resume, stale proposals and independent provider selection. A neutral live call verifies actual credentials only when available. Provider success and literary/semantic acceptance remain distinct.

## V — Full viewport review

- Review the actual integrated build at relevant full-window sizes, including timeline switching, long/bilingual text, graph and ports, connected-data inspection, pending/stale proposals, provider failures, save/conflict messages, scrolling and keyboard focus.
- Record exact build, edition, viewport, observed results and screenshots; inspect native scaling, IME, accessibility and print/export where available. Record unavailable capabilities as not reviewed.
- **Gate:** critical controls and warnings are accessible without clipping; interactions operate on the displayed revision; unresolved usability failures return to their owning integration step.

## E — Authoring and recomputation exercises

- First exercise a neutral, fixed two-character fixture through text, form data, recomputation, composition, conditioning, explicit decision and save/reload, including an unsupported transition and an external-edit conflict.
- Then exercise the available Episode 0, Spring Break, Hot Scoomp and partial Tapped Out material as separate editions. Review source evidence and previously unverified state observations; do not merge alternate versions or add the planned but unwritten continuation as canon.
- **Gate:** record the selected inputs, expected/observed outcome, evidence location, source hashes and author decision for each exercise. Track missing character datasets, unreviewed causes, unrun provider paths and unsupported document formats as open—not successful—work.

## The actual workflow to recover

```text
Author selects one source edition
        │
        ▼
Editable Tiptap draft + formatting + stable source/block identity
        │                     │
        │                     ├──► Source evidence index ──► character/form graph
        │                     │                               │
        │                     │                      actor + chosen form data ports
        │                     │                               │
        │                     └───────────────────────────────┤
        │                                                     ▼
        │                                  modeled facts, beliefs, props and reactions
        │                                                     │
        ├─────────────────────► author-selected beat ─────────┤
        │                                                     ▼
        │                                       composer draft proposal
        │                                                     │
        ├─────────────────────► selected prose span ──────────┤
        │                                                     ▼
        │                                      conditioner proposal
        │                                                     │
        ▼                                                     ▼
Revision-bound validation and side-by-side review ◄──── proposal history
        │
        ├── reject / keep as hypothetical / leave pending
        └── accept one change → unsaved draft → recoverable save → reload
```

Every arrow must name the same edition and the revision on which it depends. A provider receives only the explicitly selected prompt/context; neither an output page nor a graph refresh owns or regenerates the author's text. A hypothetical reaction or draft is not an accepted event. A form cue can be evidence for an observation, but it cannot establish its own cause.

### Ownership contracts

| Artifact | Authoritative owner | Carries | Failure behavior |
|---|---|---|---|
| Original source and alternate editions | Preserved source files and timeline manifest | Source file/hash, edition, chronology relationship, partial/variant status | No command rewrites the original during an analysis or proposal exercise. A variant is not merged merely because filenames or characters match. |
| Editable document | Working story text plus its rich-document and identity sidecars | Text, visual marks, stable IDs, revision, source relationship | Conflict rather than silent import, identity reset, or overwrite when sidecars are inconsistent. |
| Character definitions | Actor registry and form IDs | Actor identity, forms, cue aliases, graph/data-port IDs and versioned definitions | Unknown actors and forms remain visible candidates until the author adds or reviews them. |
| Character datasets | Pinned local packages and explicit actor/form bindings | Owner, data domain, schema, revision, content hash, review status and source provenance | Missing, stale, conflicting and unsupported inputs are reported separately; no traits are invented. |
| Story/world state | Edition-scoped manifest plus reviewed observations | Beat goals, accepted state, facts/beliefs/props where actually modeled, evidence and cause review | An empty manifest reports unmodeled coverage; an inferred cue does not update approved history by itself. |
| Generated work | Durable proposal/job records | Base text/rich/graph revisions, target, original and candidate, provider/model, checks, decision and stale state | Failures, late responses and rejected candidates remain recoverable and cannot silently alter the draft. |
| Save/recovery | Revision and recovery-journal layer | Expected hashes, complete updates, ownership of journal and target files | A concurrent or interrupted operation either commits a coherent revision or returns a visible conflict with recoverable prior bytes. |
| HTML/graph exports | Individually identified run artifacts | Input identities, generation settings, reports and reader/graph output paths | A new run receives a new location or refuses an occupied/protected destination. |

### Character and form requirements

The actor ID is the continuous character path. Each transformation has its own stable form ID and data port; selecting a form is not a claim that its personality must differ from the base. The available forms to preserve and review include:

- **Rainee:** base, the six individually addressable Episode 0 celebrity forms, and the Peter-Rainee form. The older grouped form is retained for compatibility until an explicit migration is reviewed.
- **Stella:** standard, 20%, 40%, 70%, legacy 80%, and her Big Tiddy Steve form. The author described Steve as Stella's own Steve-like persona with Stella's memories. The 120–150% description must be mapped to the appropriate form/evidence rather than used to invent additional events.
- **Haley:** standard, Roger-related form, and the BBL influencer form. `hayley` in the legacy profile is an alias of graph actor `haley`; identity mapping must not combine a different actor's traits.
- **Francine:** base, nurse form and J.Lo-rump form. Each has a distinct form port.
- **Other characters:** expose candidate speakers and allow author-reviewed additions with their own actor/base-form IDs and unbound ports. A discovery cap or heuristic match is not a complete cast list.

For every actor/form, resolve each domain once:

| Mode | Required effective data |
|---|---|
| `inherit` | Use actor data for that domain. A form cannot silently contain ignored local bindings. |
| `extend` | Combine non-overlapping actor and form domains. An overlap is a visible conflict unless an explicit resolver exists. |
| `override` | Replace only domains explicitly supplied by the form; retain unrelated actor domains. |
| `replace` | Use only form-bound data. Empty or profile-only replacement cannot fall back to embedded actor behavior or personality. |

The supported local adapters are source indexes, dialectic profiles and explicit reaction rules. Future Deep Character/Super JSON data needs its actual supplied schema, version, validation and migration contract before it can drive computation. `resolved` means a particular reference loaded; display separate capabilities for source evidence, profile and reaction behavior, including review status and freshness.

## Issue-by-issue repair register

Statuses below distinguish the candidate code written during this recovery from a completed acceptance gate. Focused fixture evidence is not a full-timeline or production qualification.

| ID | Problem / owner | Current evidence and state | Required closure |
|---|---|---|---|
| R01 | Pending proposal loss — `editor.py`, `proposal_store.py`, editor UI | Candidate per-edition SQLite history and explicit reject/restore actions were added. A focused neutral HTTP exercise retrieved proposals after another plan, section switch and server restart. | Test multiple processes, stale text and formatting, saved versus unsaved acceptance, rejection, database damage/full disk, retry after acknowledgement loss, workspace copy/rename and UI restoration. Preserve a provider answer if history persistence fails. |
| R02 | Corrupt or partial identity map — `compiler/identity.py`, `store.py`, editor load/save | Candidate loader distinguishes absent from invalid/malformed; a neutral HTTP check returned a conflict without changing source or sidecar. Historical duplicate-ID migration remains a separate case. | Exercise unreadable, invalid Unicode/JSON, wrong field types, partial/empty maps, duplicates, edited/moved duplicate lines and recovery from a valid prior map. Confirm no silent reference reassignment or sidecar replacement. |
| R03 | Non-atomic cross-process saves and recovery — `persistence.py` | Candidate OS-held local locks now cover journal and target paths. Neutral multi-process checks exercised competing writers, a blocked live recovery and recovery after a terminated writer. | Verify shared character files across different edition journals, corrupt/missing backups, lock timeout, process crash at each commit phase, copied/legacy journals and concurrent readers. Define OneDrive/multiple-machine ownership separately: local locks cannot coordinate remote sync clients. |
| R04 | Generated output overwrites — `run_pipeline.py`, `graph/pipeline.py`, `html_compiler.py`, convergence harness | Candidate output creation refuses existing files and uses unique convergence run folders; focused sentinel checks passed. | Inventory **every** CLI/editor/export path, source/sidecar aliases, symlinks and partially written output. Record a run manifest; protect against two processes selecting one destination. Qualify intentional replacement only with an explicit, revision-checked operation. |
| R05 | Provider requests block editor work — `editor.py`, `editor_ui.py` | Candidate freezes a store snapshot and releases the local commit lock for provider work. A barrier-based neutral HTTP check saved while a provider was blocked and retained the late result as stale. | Exercise the real browser with typing, formatting, saving and edition switching while blocked; test simultaneous requests, provider timeout, cancellation and late result after restart. Confirm the snapshot includes all data dependencies and no later response changes current state. |
| R06 | Form replacement accidentally inherits actor data — `data_ports.py`, `workspace.py` | Candidate stops embedded behavior and embedded personality fallback for an empty form replacement; focused tests exercise inheritance versus replacement. | Test all four modes across source, profile and behavior domains, multiple packages, conflicts, missing files, aliases, hash changes and cache invalidation. Inspector, evaluator and composer must report the same effective inputs and provenance. |
| R07 | Source/cast coverage — graph discovery, `cast_candidates.py`, editor | The master has seven configured actors plus 16 discovered **candidates**. Candidate UI can add a reviewed actor/base port in a sandbox; it does not create personality data. | Qualify the source locator/hash, candidate cap, ambiguous aliases, false cues, manual cast entry, separate-edition identity and save/reload. Add actors only after author review; missing profiles and functions stay explicit. |
| R08 | State and transition errors — `extract.py`, `checks.py`, form review | Master: 161 cue/state mismatches and 17 unverified events. One grouped-Rainee return pattern was corrected; remaining findings are unresolved. | Group by actor/form and source location; distinguish false pattern, missing starting state, correct observed form, missing cause, unsupported transition and contradictory evidence. Review a source observation separately from approving a causal edge. Re-run each edition after recorded decisions. |
| R09 | Hypothetical form versus accepted history — `composer_engine.py`, `workspace.py` | Candidate can return a hypothetical form draft with an explicit pending-transition state and refuse direct application when it differs from accepted history; focused neutral fixture passed. | Check every mismatch/cause type, no-cue prose, stale reviews, unrelated graph errors and explicit author transition review. Provide a usable review path before eligibility; do not silently promote the scenario into canon. |
| R10 | Rewrite semantic drift and false flags — `condition.py`, `prose/validation.py`, recook | Venice returned eligible candidates that added or changed details. The “Together” name false positive and bounded length prompt were addressed for tested examples. | Protect named subjects, actions, locations, object ownership, numbers, dialogue and authored exclusions. Show uncertain or changed claims to the author; a mechanical pass remains review eligibility, never a proof of meaning or prose quality. |
| R11 | Inconsistent entry points and success labels — runner, CLI, editor and harness | The main runner performs graph/diagnostic/reader work; it does not perform a complete model composition and conditioning pass. Different commands have different scopes. | Provide a stage-by-stage report with passed, failed, not run, not modeled, pending review and stale. Every write path uses the same proposal/revision rules. No “complete” label when a required stage or world model is missing. |
| R12 | DeepSeek, Venice and session history — provider adapters and session/UI | A neutral DeepSeek API request succeeded; offline candidate tests cover stateless history resume, archiving and a session conflict. Venice worked on seven selected non-explicit samples. | Test editor → session → composer/conditioner → proposal with fake transport and a neutral live call; verify model identity, refusal/truncation handling, concurrent histories, credential isolation, timeouts and no automatic provider switching. Never claim a session is live merely because a key exists. |
| R13 | Rendering, formatting and viewport — Tiptap/editor/reader | Previous sandbox tests covered basic formatting, save/reload and three headless viewport sizes. The newest combined build is not fully reviewed. | Qualify source/rich sidecar mapping, inline text, split/merge, mixed formatting, undo boundaries, export fidelity, native scaling, keyboard, IME/CJK and full-window views. Mark unsupported DOCX/PDF and graphic-layout features explicitly. |
| R14 | Legacy audit regressions — all owning modules | Earlier findings F01–F22 include identity, scene membership, stale cache, cue self-authorization, provenance, state deltas, offsets and HTML escaping. Several recovery changes and focused tests exist. | Re-run each original adversarial case through the current production entry point; record result and build, not just a test name. Preserve the earlier report as historical evidence. |
| R15 | Configuration and credential handling — local settings, providers | The project contains git-ignored live credentials; the DeepSeek key was shared in chat. Current editor instances can run older code than the checkout. | Keep credentials out of source, outputs and logs; rotate exposed keys and update local settings. Identify server build and workspace in the UI and evidence. Avoid restarting or replacing an editor with possible unsaved work. |

## Crosswalk to the original 22 findings

The [original audit](<C:/Users/User/.codex/visualizations/2026/11/02/01a19a0f-cb3a-7863-99c0-1ce0aae956b7/narrative-composer-review/REVIEW.md>) records the original triggers and evidence. This is a regression work list, not a statement that every finding is still present or that an earlier correction is qualified. Record a fresh result for each finding on the integrated build, including an author-facing check where applicable.

| Audit ID | Repair owner in this plan | Required regression evidence |
|---|---|---|
| F01 | R10–R11 | Condition a passage whose proposed rewrite reverses actions and locations; the changes remain visible for review, and empty world coverage cannot be called semantic approval. |
| F02 | R10–R11 | Run neural recook with a destroyed prop; it passes through the shared invariant/proposal gate, then rechecks the assembled result. |
| F03 | R08–R09 | A form cue without an approved cause produces an observation and finding, not a self-authorized state transition. |
| F04 | R07–R08 | Discover an unknown form and transition; neither becomes a legal transition until reviewed through the authoritative graph path. |
| F05 | R06, R14 | Change only character or world definitions, recompute with a reused network, and compare with a cold rebuild; dependencies and affected results must agree. |
| F06 | R11, R14 | Supply missing prerequisites, a cycle, an unmet belief and an invalid prop state; each blocks the affected beat with an actionable result. |
| F07 | R02–R04 | Inject validation and commit failures, and run multiple iterations with `in_place=False`; all related files remain coherent and original source bytes stay unchanged. |
| F08 | R02, R13 | Edit the cue and dialogue separately when they share a source line; both edits survive projection, save and reload without duplicating or dropping text. |
| F09 | R06, R14 | Round-trip a character containing deprecated states/transforms and a non-default voice profile; every field and status remains intact. |
| F10 | R06–R07, R14 | Ingest observations for two identities and a model response with invented source/time bounds; only explicitly mapped, source-supported evidence is retained. |
| F11 | R13–R14 | Rebuild a document with scenes and blocks; every applicable block has a valid scene edge and missing endpoints are reported. |
| F12 | R02, R13 | Open a preview and editor for the same revision; visible blocks resolve to the same persistent IDs used by store operations. |
| F13 | R02, R06, R14 | Change only source identity or sidecar revision and rebuild with a warm cache; the result matches a cold build with no borrowed IDs or metadata. |
| F14 | R11, R14 | Change an unsaved manifest/world value and run diagnostics; displayed findings reflect the current in-memory revision before and after save/reload. |
| F15 | R08, R14 | Extract a line mentioning two changing actors; preserve separately scoped evidence and ordered events for both. |
| F16 | R08, R14 | Traverse an explicitly reversible transformation back to the original form; emitted source and destination follow the actual traversal. |
| F17 | R11, R14 | Force graph errors or a graph-check exception after other stages pass; the overall result cannot report convergence or zero errors as if the graph passed. |
| F18 | R02, R13 | Edit a document with leading blank lines and mixed line endings; source offsets still point to the intended text and round-trip faithfully. |
| F19 | R02, R06, R14 | Submit JSON with omitted or altered immutable IDs, including item IDs; reject the whole edit without mutating an owner or dropping identity. |
| F20 | R10, R13 | Put HTML-like source and provider strings in a review page; text renders as text with no executable markup. |
| F21 | R07, R11 | Analyze an empty intake manifest; unmodeled facts, props, beats and causality are labeled unknown rather than reported verified. |
| F22 | R13–R14 | Inspect bilingual/CJK samples; report supported diagnostics and unsupported language behavior separately, then test editing and rendering independently of prose scores. |

## Inputs and decisions that cannot be fabricated

- **Character data:** the actual Deep Character/Super JSON schemas, versions, ownership and datasets are not available in this handoff. Existing source evidence and legacy profiles remain usable as labeled inputs, but they are not a complete reaction model. Implement and test the port contract with clearly marked fixtures while awaiting real records.
- **Story and causality:** the author must review ambiguous actors, form observations and transition causes. The available Tapped Out versions are partial alternatives; the planned basement event is not implemented story evidence. Keep Stella's Steve form tied to her identity and memories, and do not invent the excluded breast-milk storyline.
- **Document needs:** verify the desired graphic layouts and the current editing/export capabilities with actual representative documents. Do not promise DOCX/PDF round-trip, arbitrary layout or lossless formatting until each is demonstrated and any unsupported features are made visible.
- **Deployment and providers:** distinguish the changed checkout from already-running editor processes. Confirm which build is tested, and keep local credentials private; a working API key does not establish an end-to-end application workflow.

## Detailed implementation sequence and dependencies

### Phase 0: controlled baseline

1. Record the current working tree, untracked recovery files, each running editor's port/workspace, and the source hashes already available. The loaded server build and the files on disk are separate observations.
2. Define an isolated candidate workspace and separate run-output root. Preserve source files and previous outputs. Keep the original and every Tapped Out edition in the timeline with its existing source identity.
3. Re-run the existing small regression set and record exact command, build and skips. A pre-change passing suite is a baseline, not validation of subsequent work.

**Output:** a baseline inventory and a source-protection ledger. **Dependency:** none. **Exit:** a fresh candidate can be inspected without altering the author's originals.

### Phase 1: authored-work protection

1. Establish one durable proposal record and stable proposal/job IDs for all three paths: composer, conditioner and recook. Preserve both successful and held candidates, their cause, and the author's decision. A repeated HTTP acknowledgement must not silently generate or discard another result.
2. Treat a corrupt existing identity map as a recoverable conflict. Provide a reviewable recovery workflow rather than resetting IDs. Bind identity maps and reviews to source/edition revisions.
3. Coordinate local multi-process save **and recovery**; validate journal ownership and every backup before touching a target. Make all related files participate in a single recoverable revision. Capture slow-provider input before releasing locks, then publish against that captured revision.
4. Give readers and graph artifacts unique run identities and protected destinations. Include the output locations in the result; refuse aliases of source, sidecar, dataset, secret or previously authored output files.

**Output:** recoverable editing/proposal pipeline. **Dependency:** Phase 0. **Exit:** the failure cases in the acceptance matrix pass without relying on a particular model.

### Phase 2: graph and data ownership

1. Reconcile the actor/form registry and port IDs with the author's named forms. Keep compatibility IDs explicit; avoid copying a form into a second actor path.
2. Resolve data domains in one place, including any legacy embedded data. Validate dataset identity, owner/alias, schema, content hash, review status and edition scope. Make the graph inspector, evaluator and composer consume that same resolved result.
3. Add source evidence and candidate-cast review without promoting a lexical hit to a personality claim or approved event. Preserve the distinct identities of alternate source versions.
4. Review the actual graph errors by grouped cause. Use source locations and hashes; let the author accept a form observation, reject it or defer it, and separately inspect or approve its causal transition. Do not approve a cause just to make a report green.
5. Specify the future data interface for more complex personality/functions. Implement only adapters whose real schemas and input ownership are available.

**Output:** a source-linked, data-port graph with explicit unknowns. **Dependency:** Phase 1. **Exit:** correct form-specific data affects only dependent proposals; the 178 master findings are classified with honest remaining review items, not assumed resolved.

### Phase 3: composition, conditioning and model sessions

1. Define the proposed-beat contract: selected authored beat, active actors, chosen actual or hypothetical forms, effective data versions, modeled world knowledge/props, source context and intended output scope.
2. Run the composer and conditioner through the same immutable proposal boundary. Recheck current source, formatting, graph and world revision at application time. An exploratory hypothetical candidate may be viewed, but approval of its form/transition is a separate author decision.
3. Add meaning-oriented checks where deterministic evidence exists, while retaining an explicit author review for uncertain changes. Preserve exact protected dialogue and distinguish mechanically eligible from semantically accepted.
4. Complete and verify the existing DeepSeek API session and the Venice adapter. Use neutral fixtures for integrated transport tests; record the actual provider/model and response completion status. No automatic fallback, no credential in a prompt, and no automatic full-story generation.

**Output:** reviewable, revision-bound model proposals. **Dependency:** Phases 1–2. **Exit:** the same gates operate through editor, CLI and any batch path; provider failure, refusal, truncation or stale data cannot silently commit prose.

### Phase 4: integrated viewport review

Review the full app using the same candidate build and workspace. At minimum record 1280×800, 1600×1000 and 1920×1080 browser viewports, plus native display scaling and input methods when available. Cover editor, timeline selector, all-character and selected-form graph, source/cast inspector, data-port status, proposal history, stale/rejected decisions, save state, error messages and provider progress. Inspect full-window screenshots as well as interactions; record unavailable IME, accessibility and print checks as open.

**Output:** viewport findings and evidence. **Dependency:** Phases 1–3. **Exit:** no critical clipping, inaccessible controls, misleading status or mismatch between displayed and edited revision; return any such finding to its owning phase.

### Phase 5: authoring and recomputation

1. In a disposable neutral fixture, author a beat; bind a distinct form dataset; compute a proposed reaction; generate a composer candidate; condition a selected span; reject one candidate and accept another; save/reload; verify unrelated text, identities, world facts and another actor's result.
2. Repeat source-appropriate graph and recomputation checks on each available timeline entry. Process the master and its overlapping sections as related editions, not additive text. Keep each partial Tapped Out outline and story variant separately attributed.
3. Review the graph error clusters against the actual evidence. Record each author's decision, unresolved cause and missing dataset. Conduct appropriate bounded live-provider exercises only on independently reviewed passages; full-text local diagnostics are distinct from full-story model writing.
4. Re-hash original sources and compare them with the baseline. Report expected and observed behavior, pending proposals, any changes to working copies, and all unmodeled/unrun stages.

**Output:** a reproducible exercise report and review queue. **Dependency:** Phases 1–4. **Exit:** source integrity holds and the outcome identifies what is working, awaiting human data/review, or still blocked.

## Acceptance matrix

| Case | Trigger | Required result |
|---|---|---|
| A01 | Plan A, then B, switch editions, restart | A and B remain discoverable by ID in their original edition; source unchanged. |
| A02 | Reject, restore, accept and save a proposal | Each decision is explicit and durable; accepting affects only the intended revision and target. |
| A03 | Provider succeeds while the author edits or saves | Save remains responsive; the answer is retained as stale, not applied to a different revision. |
| A04 | Crash after proposal persistence before response reaches the browser | The recorded job/proposal can be recovered without silently replacing it or duplicating the change. |
| A05 | Corrupt or partially valid identity sidecar | Visible conflict; original text and sidecar bytes remain intact; no silent ID regeneration. |
| A06 | Two local processes save from the same base | Exactly one coherent result wins; the other receives a conflict. |
| A07 | One writer is paused after journal preparation while another opens the project | Recovery does not roll back the live writer; after a killed writer, an authorized recovery restores a coherent revision. |
| A08 | Existing reader/report output or output path aliases an input | Run refuses the destination or allocates a new output; prior artifact and input remain unchanged. |
| A09 | Actor rule plus form `replace` with no local behavior | No inherited rule or profile leaks into the replaced form. Other port modes follow the domain table above. |
| A10 | Changed package, wrong owner or unsupported schema | The affected input becomes stale/unresolved; no fabricated reaction and no stale cached reuse. |
| A11 | Cue asserts a form without an accepted cause | Observation and diagnostic remain visible; no automatic legal transition. |
| A12 | Hypothetical form differs from accepted history | Candidate can be inspected as hypothetical; acceptance cannot silently approve the form or cause. |
| A13 | Rewrite reverses an action, moves an object or adds a new fact | Existing protections report what they can; unresolved meaning stays in author review rather than being declared correct. |
| A14 | DeepSeek/Venice timeout, refusal, truncated response or session conflict | No automatic provider switch or prose commit; the error and any recoverable answer remain visible. |
| A15 | Tiptap formatting, bilingual edit, split/merge, undo, save and reload | Text/format/identity relationships survive; unsupported cases are explicitly blocked or flagged. |
| A16 | Full timeline analysis | Each edition and its source hash remain identifiable; the master/section overlap and partial alternate versions are not double-counted as new story. |
| A17 | Viewport review with large graph and proposal history | All findings remain reachable and warnings legible; no clipped controls, stale hidden decisions or unreviewed surface marked passed. |

Use neutral, disposable fixtures and deterministic barriers for failure and concurrency tests. Live model calls are for transport/integration evidence on suitable reviewed inputs, not a substitute for adversarial tests or author review.

## Research basis and constraints

The requested research agent independently confirmed the proposal-memory, identity-map, shared-lock, output and port-resolution boundaries in the current code. It recommends a shared ownership protocol for **both save and recovery**, plus append-only proposal identity and explicit revision scope. Its findings inform R01–R09 above.

The supporting platform limits are documented by the primary sources: [Python thread locks](https://docs.python.org/3/library/threading.html) are process-local; [file replacement](https://docs.python.org/3/library/os.html#os.replace) alone does not make a preceding hash check an atomic multi-process transaction; [SQLite isolation](https://www.sqlite.org/isolation.html) serializes writers, while its [WAL documentation](https://sqlite.org/wal.html) limits shared WAL use across hosts. [DeepSeek's multi-round API](https://api-docs.deepseek.com/guides/multi_round_chat/) is stateless, so the application owns the history it resends. These sources support the design constraints; they do not prove this implementation is complete.

## Definition of done for this recovery

The integration gates and requested viewport/exercises must have concrete evidence on the same build. A remaining missing dataset or unresolved author decision must be reported as a limitation rather than fabricated or counted as a code fix. Existing tests remain useful evidence only for the revision on which they ran.
