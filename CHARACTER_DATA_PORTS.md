# Character graph and data ports

The actor root is the parent of its separately addressable forms. The optional `rainee.state.peter_50` has its own data port and provisional links between base and Peter; this is an available author-defined option, not a claim that the intermediate appeared in the source. The legacy direct base-to-Peter path and existing form IDs are retained. No rules or personality were fabricated for the new state.

In the editor, inspect a character root and choose **Inspect character trace** to see cue-linked dialogue, candidate lexical action and outline-note mentions, and state availability in the selected edition. Open a source block to inspect it. A lexical name match is not proof that a person performed an action; notes are not automatically dialogue or completed events. **Add form to character** creates an unsaved option and data port without creating a story observation or approving a transition. **Connect character forms** creates a provisional possible link between two forms of that actor. The graph displays defined links separately from observed story transitions. The form inspector also offers **Inspect appearances in text**. Long traces are paged; the filter applies to loaded rows.

The composer can use a bounded sample of linked authored text even if no personality or behavior package is attached. Samples are source data, not instructions or approved interpretations. The future Super JSON/Deep Character boundary and the locally found design references are recorded in [future character data](FUTURE_CHARACTER_DATA_BOUNDARY.md).

Each character has one actor ID, a data port on that actor, and one unique ID and data port for every configured form. The editor's **Character graph → Characters & forms** view lists them, including forms that have not appeared in the open story. Select a port to inspect or edit its JSON. The Story Graph and Horizontal Trace remain available for observed story events.

Stella's `stella.state.big_tiddy_steve` belongs to the `stella` actor. The source-specific description says her Steve form changes her behavior while preserving her memories. That description is not a Deep Character dataset. The requested 20%, 40% and 70% forms have separate IDs; the old 80% form is retained for compatibility. Rainee's six Episode 0 celebrity forms have separate IDs alongside the legacy grouped form and Peter form. Individual form IDs do not automatically approve transition causes.

## Port modes

- **inherit:** use the actor's bindings. An inherited form port may not also hold local bindings.
- **replace:** use only the bindings on this form. An empty replacement explicitly supplies no data.
- **extend:** combine the actor's bindings with this form's bindings when their data domains do not overlap. Conflicting domains are reported rather than silently merged.
- **override:** replace only the domains explicitly bound on this form, while inheriting the actor's other domains. For example, a form-specific personality can replace the actor's personality while retaining that actor's source index.

An empty port is `unbound`. A reference to a missing file, unsupported schema, changed hash or invalid package is `unresolved`. Overlapping bindings are `conflict`. These states are visible; the character evaluator will not silently make up a result. A small explicit `attributes.behavior_rules` fixture may still be evaluated when no package is bound. It is not a Deep Character model.

## Plugging in a supported local test package

The loader supports `narrative.behavior.v1` (`behavior_rules`), `narrative.dialectic.v1` (`personality_profile`), and `narrative.story-index.v1` (`story_evidence`). The following is a neutral behavior-rule example, not story or personality data:

```json
{
  "dataset_id": "example_reactions",
  "revision": "1",
  "schema_id": "narrative.behavior.v1",
  "owner_id": "example_character",
  "review_status": "pending_review",
  "rules": [
    {"rule_id": "ask", "event": "challenge", "response": "The character asks for clarification."}
  ]
}
```

1. Save the JSON as `character_data/example_reactions.json` next to the open story file. The loader only reads files inside this directory.
2. Compute the exact SHA-256 of that file, for example in PowerShell: `Get-FileHash -Algorithm SHA256 character_data/example_reactions.json`.
3. In the actor or form port inspector, keep its existing `id`, select the mode, and add a binding with `dataset_id`, `revision`, `schema_id`, `domain` (`behavior_rules`), `relative_path` (`example_reactions.json`), and `content_hash` (the computed hash). Save the workspace.
4. Open **Character reactions**, enter the matching event and optionally select a form for a hypothetical scenario. The result is a proposal, not an accepted event. Replacing a form package changes that form's dependent reaction calculation; unrelated actor data remains independent.

Changing the file without updating the reference makes the port unresolved. Unknown schemas are retained as references but cannot yet drive a reaction. The future Deep Character/Super JSON format and a loader for it have not been supplied or implemented.

Behavior packages must name their owning actor and have `review_status` set to `pending_review` or `approved`; set the example owner to the actual actor ID. Older packages without this information remain intact but unresolved until reviewed and rebound with a new content hash. Shared or generic behavior packages require an explicit future scope contract; the loader does not silently attach one character's rules to another. Pending rules can inform an exploratory proposal but do not become approved story facts. Legacy embedded actor domains participate in form-mode resolution: an overlapping `extend` is a conflict, while `override` explicitly replaces only the bound domains.

## Rebuilt timeline connections

The fresh workspace `out/venice_graph_restart_20261101_01` connects each of the seven configured actors to an edition-scoped source index. Its block IDs, lines and hashes are lexical mention candidates, not approved facts, causal transitions or evidence that the actor appears in every edition. A changed source is marked stale. The master overlaps several separate section editions; keep those identities separate.

Rainee and Haley also have their existing dialectic profiles connected as **pending review**. `hayley` in the legacy profile is an alias of graph actor `haley`. The compatibility adapter preserves the original profile and leaves missing confidence and provenance unknown. The other five actors have source evidence only. All seven currently lack authored behavior-rule packages, so an evidence connection does not by itself compute personality or a reaction.

`resolved` means the referenced packages loaded and passed their identity and content-hash checks; it does not mean their claims are approved or a reaction model exists. Actual graph nodes connect ports to datasets through `binds_dataset`; form ports show inheritance through `inherits_data_from`. In **Nodes & diagnostics**, select a data port and use **Inspect connected data** to see its packages and current-source references. Dataset nodes are derived and are not edited in place.

For a new beat, **Draft forms** selects a hypothetical form per active character and supplies its effective profile, rule data, form ID, and configured speaker cues to the composer. This is a drafting assumption, not an approved state transition. Composition still checks the result against the actual story graph, and a proposal remains pending until the author reviews it.

## Reviewing observed forms

Story cues and authored state markers are observations; they cannot approve their own transition. In **Nodes & diagnostics**, an author can accept an observed form for that source line. The decision is tied to the evidence text and saved with the section manifest. The form is then available as a reviewed state, while the transition cause remains pending. Editing the evidence makes that review stale and visible for re-review. Section starting states are also scoped to the section manifest; the timeline exercise's boundary selections are marked pending author review.

The current Tiptap editor handles text and visual formatting. Undo is paused while structured graph or beat changes are unsaved; see [document engine status](DOCUMENT_ENGINE_STATUS.md) and the [document engine plan](DOCUMENT_ENGINE_AND_GRAPHITE_PLAN.md) for the implemented and planned boundaries.
