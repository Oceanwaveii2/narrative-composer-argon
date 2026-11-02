# Recover an identity-sidecar conflict

An identity conflict means the editor cannot safely associate blocks with their previous IDs. It stops before saving; the message does not establish which file is correct.

1. Stop editing the affected edition. Do not discard an unsaved browser draft: copy it somewhere separate first. Leave other editor sessions untouched.
2. Copy the story, its adjacent `.ids.json` file, rich-document sidecar, revision journal, proposal history, and related graph files into a new recovery folder. Preserve the current originals and record their hashes. Do not delete or regenerate the identity map to make the error disappear: existing graph links and proposals may depend on its IDs.
3. Locate a known matching story and identity sidecar from the same saved revision. Compare the saved story bytes, block text and IDs, and any relevant formatting sidecar. A similarly named edition or a map from before an external edit is not sufficient evidence.
4. Work on another copy. Restore the matching pair there, open it, inspect the text, formatting, graph links, and proposal history, and compare it with the preserved draft. Bring intentional edits across under review; do not silently replace the newer story with an older backup.
5. If no matching pair can be identified or repeated blocks make the mapping ambiguous, leave the conflict unresolved and request an author-guided reconciliation. Automatic proximity matching cannot prove which block is which.

Proposal histories are scoped to their original edition paths; copying them to a recovery edition does not authorize applying them there. Graph definitions may be shared by editions, so back them up before any change.
