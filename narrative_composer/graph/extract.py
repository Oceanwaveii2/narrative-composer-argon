"""Evidence-aware extraction. Cues assert state; they cannot authorize transitions.

Explicit author event notes use > EVENT: pulse. Configured transforms may also
supply approved attributes.trigger_patterns. Unrecognized causes stay unverified.
"""
from collections import defaultdict
import hashlib
import re
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.ids import state_id
from narrative_composer.graph.models import StateInstance, StoryTime, TransformInstance, Violation
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.models.ast_nodes import ASTNodeType

class RunResult:
    def __init__(self):
        self.states = []
        self.xforms = []
        self.unresolved_cues = []
        self.canon_leaks = []
        self.observations = []
        self.issues = []

def extract_run(elements, graph: StoryGraph, canon: str, run_id: str, initial_states=None,
                reviewed_observations=None) -> RunResult:
    res = RunResult()
    resolver = EntityResolver(graph, canon)
    unconstrained = EntityResolver(graph, canon=None)
    current = {eid: ent.attributes.get('canon_base_states', {}).get(canon, ent.base_state)
               for eid, ent in graph.entities.items() if not ent.canons or canon in ent.canons}
    initial_states = initial_states or {}
    if not isinstance(initial_states, dict):
        raise ValueError('Initial character states must map actor IDs to state IDs')
    for eid, sid in initial_states.items():
        if eid not in current or not isinstance(sid, str):
            raise ValueError(f'Initial state names an unknown or out-of-scope character: {eid}')
        entity = graph.entities[eid]
        state = next((s for s in entity.states if s.id == sid and s.status == 'active'), None)
        if not state or (state.canons and canon not in state.canons):
            raise ValueError(f'Initial state {sid} is not an active form of {eid} in {canon}')
        current[eid] = state.slug
    reviews = reviewed_observations or []
    if not isinstance(reviews, list):
        raise ValueError('Reviewed observations must be a list')
    review_keys = []
    for review in reviews:
        if not isinstance(review, dict) or any(k not in review for k in ('kind','entity','state_id','line','evidence_hash')):
            raise ValueError('Malformed reviewed observation')
        review_keys.append((review['kind'],review['entity'],review['state_id'],review['line'],review['evidence_hash']))
    if len(set(review_keys)) != len(review_keys):
        raise ValueError('Duplicate reviewed observation')
    review_keys, used_reviews = set(review_keys), set()
    seen, consumed = set(), set()
    counts, xf_counts = defaultdict(int), defaultdict(int)
    events = {}
    scene = 0
    def emit(eid, slug, el, source):
        counts[eid] += 1
        res.states.append(StateInstance(id=f'run.{run_id}.{eid}.inst.{counts[eid]}', entity=eid,
            state_id=state_id(eid, slug), at=StoryTime(scene_index=scene, line=el.line_number),
            source=source, evidence=el.content[:120]))
    def appear(eid, el):
        if eid not in seen:
            seen.add(eid)
            emit(eid, current[eid], el, 'initial' if eid in initial_states else 'base')
    def observe(eid, state, el, kind):
        sid = state_id(eid, state)
        evidence_hash = hashlib.sha256(el.content.encode('utf-8')).hexdigest()
        key = (kind,eid,sid,el.line_number,evidence_hash)
        if key in review_keys:
            used_reviews.add(key)
            if current[eid] != state:
                previous = state_id(eid, current[eid])
                current[eid] = state
                emit(eid, state, el, 'reviewed')
                res.issues.append(Violation(rule_id='G9_REVIEWED_STATE_CAUSE_PENDING',severity='WARNING',
                    line=el.line_number,entity=eid,
                    message=f'Author reviewed {sid} in the source; the transition cause from {previous} still needs review.',
                    suggestion='Review causal evidence and transformation definitions separately.'))
        res.observations.append({'kind':kind,'entity':eid,'state':state,'line':el.line_number,
            'evidence':el.content[:120], 'evidence_hash':evidence_hash,
            'accepted':state == current[eid], 'reviewed':key in review_keys})
    for el in elements:
        if el.node_type == ASTNodeType.SCENE_HEADING:
            scene += 1
            events.clear()
            continue
        if el.node_type == ASTNodeType.NOTE:
            match = re.fullmatch(r'EVENT:\s*([\w.-]+)', el.content.strip(), re.I)
            if match:
                events[match[1]] = el.line_number
            # An authored state-marker pattern explicitly identifies its owner;
            # it can appear immediately after a continuous scene heading.
            matches = [(eid, state) for eid in seen for state in graph.states_of(eid, canon)
                       if any(re.search(p, el.content, re.I) for p in state.observation_patterns)]
            if len(matches) == 1:
                eid, state = matches[0]
                observe(eid, state.slug, el, 'state_marker')
            continue
        if el.node_type == ASTNodeType.CHARACTER:
            cue = el.content.strip()
            for suffix in ("(CONT'D)", '(O.S.)', '(V.O.)'):
                cue = cue.replace(suffix, '').strip()
            eid, slug = resolver.resolve_cue(cue)
            if eid and eid in current:
                appear(eid, el)
                if slug:
                    observe(eid, slug, el, 'cue_assertion')
            else:
                # Preserve the document's existing block identities while avoiding
                # character warnings for clearly quoted lines and stage effects.
                # A configured character alias is resolved above before this filter.
                if (cue.startswith(('"', '“')) or re.fullmatch(r'\([^()]+\)', cue) or
                        re.fullmatch(r'(?:BANG|SHK-T|THWAP)(?:[!. ]+(?:BANG|SHK-T|THWAP))*[!.]*', cue, re.I)):
                    continue
                if cue not in res.unresolved_cues:
                    res.unresolved_cues.append(cue)
                other, _ = unconstrained.resolve_cue(cue)
                if other:
                    leak = f"Cue '{cue}' belongs to entity '{other}' not valid in canon '{canon}'"
                    if leak not in res.canon_leaks:
                        res.canon_leaks.append(leak)
            continue
        if el.node_type != ASTNodeType.ACTION:
            continue
        for eid in current:
            ent = graph.entities[eid]
            if not any(re.search(r'(?<!\w)' + re.escape(n) + r'(?!\w)', el.content, re.I)
                       for n in [ent.display_name] + ent.aliases):
                continue
            appear(eid, el)
            matches = [s for s in graph.states_of(eid, canon) if s.slug != current[eid]
                       and any(re.search(p, el.content, re.I) for p in s.enter_patterns)]
            if not matches:
                continue
            target = matches[0]
            before, after = state_id(eid, current[eid]), target.id
            path = graph.find_path(before, after, canon)
            accepted = path is not None and len(path) == 1 and not target.attributes.get('provisional')
            trigger = None
            if accepted:
                xf = graph.get_xform(path[0])
                accepted = not xf.attributes.get('provisional') and xf.attributes.get('origin') != 'auto'
                if xf.triggers:
                    trigger = next((t for t in xf.triggers if t in events and
                                    (eid, t, events[t]) not in consumed), None)
                    patterns = xf.attributes.get('trigger_patterns', [])
                    accepted = accepted and (trigger is not None or any(re.search(p, el.content, re.I) for p in patterns))
            res.observations.append({'kind':'state_event', 'entity':eid, 'state':target.slug,
                'line':el.line_number, 'evidence':el.content[:120],
                'accepted':bool(accepted), 'proposed_path':path})
            if not accepted:
                res.issues.append(Violation(rule_id='G8_UNVERIFIED_EVENT', severity='ERROR',
                    line=el.line_number, entity=eid,
                    message=f'Possible {target.label} in this source; its transition and causal trigger are not established.',
                    suggestion='Inspect the source observation and review any causal evidence separately.'))
                if path is None:
                    xf_counts[eid] += 1
                    res.xforms.append(TransformInstance(id=f'run.{run_id}.{eid}.xform.{xf_counts[eid]}',
                        entity=eid, xform_id=None, from_state=before, to_state=after,
                        at=StoryTime(scene_index=scene,line=el.line_number), source='unverified_observation', evidence=el.content[:120]))
                continue
            xf_counts[eid] += 1
            res.xforms.append(TransformInstance(id=f'run.{run_id}.{eid}.xform.{xf_counts[eid]}',
                entity=eid, xform_id=path[0], from_state=before, to_state=after,
                at=StoryTime(scene_index=scene,line=el.line_number), source='explicit', evidence=el.content[:120]))
            if trigger:
                consumed.add((eid, trigger, events[trigger]))
            current[eid] = target.slug
            emit(eid, target.slug, el, 'explicit')
    for kind, eid, sid, line, _ in review_keys - used_reviews:
        res.issues.append(Violation(rule_id='G10_STALE_STATE_REVIEW',severity='ERROR',line=line,entity=eid,
            message=f'Reviewed {kind} for {sid} no longer matches its source evidence.',
            suggestion='Reopen the source observation and review it again.'))
    return res
