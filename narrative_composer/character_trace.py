"""Edition-scoped, source-backed character traces, not inferred personality."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.store import registry_from_store, to_text


def character_trace(store, entity_id: str) -> dict:
    """Return conservative cue-linked dialogue and lexical action candidates.

    A name in an action does not establish who performed the action. Observed
    forms are evidence to review, not a transition or a personality judgment.
    No behavior package is required to construct this projection.
    """
    registry = registry_from_store(store)
    actor = registry.get(entity_id)
    if actor is None:
        raise ValueError('Unknown character in this edition')
    resolver = EntityResolver(StoryGraph.from_registry(registry), canon=store.meta['canon'])
    names = {actor.entity_id, actor.display_name, *actor.aliases}
    for state in actor.states:
        names.update(alias.cue for alias in state.cue_aliases)
    names = {value.strip() for value in names if isinstance(value, str) and len(value.strip()) >= 3}
    matcher = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(name) for name in
        sorted(names, key=len, reverse=True)) + r')(?!\w)', re.IGNORECASE) if names else None
    blocks = list(store.of_kind('block'))
    entries = []
    for node in blocks:
        role, speaker = node.data.get('role'), node.data.get('speaker')
        match = matcher.search(node.data.get('text', '')) if matcher and role in ('action', 'note') else None
        resolved, slug = resolver.resolve_cue(speaker) if speaker and role in ('cue', 'dialogue', 'parenthetical') else (None, None)
        if resolved != entity_id and match is None:
            continue
        kind = ('lexical_action_mention' if role == 'action' else 'lexical_note_mention') if match is not None else {
            'cue':'speaker_cue', 'dialogue':'cue_attributed_dialogue', 'parenthetical':'cue_attributed_direction'}[role]
        raw = node.data.get('raw', '')
        entries.append({'block_id':node.id, 'line':node.data.get('line'), 'role':role, 'kind':kind,
            'state_id':f'{entity_id}.state.{slug}' if slug else None,
            'text':node.data.get('text', ''), 'line_sha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            'status':('candidate outline/note mention; not an established event or dialogue' if role == 'note' else
                      'candidate mention; subject and attribution require review') if match is not None else
                     'cue-linked source; attribution and form require review'})
    run = store.meta.get('run_graph', {})
    observations = []
    for observation in run.get('observations', []):
        if observation.get('entity') != entity_id:
            continue
        line = observation.get('line')
        observations.append({**observation, 'block_ids':[node.id for node in blocks if node.data.get('line') == line]})
    instances = [item for item in run.get('state_instances', []) if item.get('entity') == entity_id]
    states = []
    for state in actor.states:
        obs = [item for item in observations if item.get('state') == state.slug]
        inst = [item for item in instances if item.get('state_id') == state.id]
        in_canon = ((not actor.canons or store.meta['canon'] in actor.canons) and
                    (not state.canons or store.meta['canon'] in state.canons))
        states.append({'id':state.id, 'label':state.label, 'port_id':state.data_port.id,
                       'mode':state.data_port.mode, 'observation_count':len(obs), 'instance_count':len(inst),
                       'availability':'observed candidate' if obs else
                           'graph state instance' if inst else 'available; no detected appearance' if in_canon else
                           'outside selected canon; no detected appearance',
                       'in_selected_canon':in_canon,
                       'provisional':bool(state.attributes.get('provisional'))})
    return {'edition':Path(store.meta['source']).name, 'edition_path':str(Path(store.meta['source']).resolve()),
            'canon':store.meta['canon'],
            'source_sha256':hashlib.sha256(to_text(store).encode('utf-8')).hexdigest(),
            'revision':store.meta['revision'], 'entity_id':entity_id, 'display_name':actor.display_name,
            'entries':entries, 'states':states, 'observations':observations,
            'notice':'Cue links and lexical mentions are source evidence, not approved behavior, motives, or transition causes.'}
