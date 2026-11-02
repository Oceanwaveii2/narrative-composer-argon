"""Stable data hubs for one actor and independently addressable forms.

These are connection contracts. They do not fabricate Deep Character/Super JSON
records or infer a personality change from a physical transformation.
"""
import hashlib
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


class DatasetRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    content_hash: str = Field(pattern=r'^[a-fA-F0-9]{64}$')
    domain: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    relative_path: str | None = None


class DataPort(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = ''
    mode: Literal['inherit', 'extend', 'replace', 'override'] = 'inherit'
    bindings: list[DatasetRef] = Field(default_factory=list)


def named_port(port: DataPort, owner: str) -> DataPort:
    expected = owner + '.port.data'
    if port.id and port.id != expected:
        raise ValueError(f'Data port identity must remain {expected}')
    port.id = expected
    return port


def effective_bindings(actor, state_id=None):
    """Resolve packaged and legacy embedded domains before any consumer uses them.

    An explicit root binding takes precedence over the same legacy embedded
    domain. A form may extend only domains absent from that effective root.
    Referenced payloads are not loaded or approved here.
    """
    root = actor.data_port
    state = next((s for s in actor.states if s.id == state_id), None) if state_id else None
    if state_id and state is None:
        raise KeyError(f'State {state_id} does not belong to actor {actor.entity_id}')
    selected = list(root.bindings)
    embedded = {name for name in ('behavior_rules', 'personality_profile') if name in actor.attributes}
    if len({b.domain for b in selected}) != len(selected):
        return {'status':'conflict','mode':'root','port_id':root.id,'bindings':[],
                'reason':'Multiple root bindings claim the same domain'}
    shadowed = embedded.intersection(b.domain for b in selected)
    embedded.difference_update(shadowed)
    source = root.id
    mode = 'root'
    if state:
        port = state.data_port
        mode = port.mode
        if mode == 'replace':
            selected, source = list(port.bindings), port.id
            embedded.clear()
        elif mode == 'override':
            overridden = {b.domain for b in port.bindings}
            selected = [b for b in selected if b.domain not in overridden] + list(port.bindings)
            embedded.difference_update(overridden)
            source = port.id if port.bindings else root.id
        elif mode == 'extend':
            # Scope/domain conflicts remain explicit; never average arbitrary JSON.
            domains = {b.domain for b in selected} | embedded
            if domains.intersection(b.domain for b in port.bindings):
                return {'status':'conflict','mode':mode,'port_id':port.id,'bindings':[],
                        'embedded_domains':sorted(embedded),
                        'reason':'Root/form data overlap in a domain, including embedded actor data; choose override or replace'}
            selected += list(port.bindings)
            source = port.id
        elif port.bindings:
            raise ValueError('Inherited form port cannot silently ignore local bindings; select extend or replace')
    if len({b.domain for b in selected}) != len(selected):
        return {'status':'conflict','mode':mode,'port_id':state.data_port.id if state else root.id,
                'bindings':[], 'reason':'Multiple bindings claim the same domain'}
    return {'status':'unresolved' if selected else 'resolved' if embedded else 'unbound','mode':mode,
            'port_id':state.data_port.id if state else root.id, 'inherited_from':source,
            'bindings':[b.model_dump() for b in selected],
            'embedded_domains':sorted(embedded), 'shadowed_embedded_domains':sorted(shadowed),
            'capabilities':sorted(embedded),
            'reason':('Pinned references require a compatible data loader.' if selected else
                      'Legacy embedded actor data is in use; it is not a bound package.' if embedded else
                      'No data is attached to this port; add a compatible package when available.')}


def load_bound_data(actor, state_id, data_root):
    """Resolve explicit, pinned local packages without interpreting unknown schemas.

    Data lives below the project's character_data directory. Supported packages are
    authored reaction rules, dialectic profiles, and edition-scoped source indexes.
    Loading a package does not approve its claims or turn source mentions into rules.
    """
    info = effective_bindings(actor, state_id)
    if info['status'] == 'conflict':
        return info, []
    if 'behavior_rules' in info.get('embedded_domains', []) and not isinstance(actor.attributes['behavior_rules'], list):
        info.update(status='unresolved', reason='Embedded behavior data must contain a rules list')
        return info, []
    if 'personality_profile' in info.get('embedded_domains', []):
        from narrative_composer.models.character import parse_compatible_profile
        try:
            profile = parse_compatible_profile(actor.attributes['personality_profile'])
            names = {actor.entity_id.casefold(), actor.display_name.casefold(),
                     *(name.casefold() for name in actor.aliases)}
            if profile.character_id.casefold() not in names:
                raise ValueError('profile belongs to a different character')
        except (ValueError, TypeError, AttributeError):
            info.update(status='unresolved', reason='Embedded personality profile is invalid or belongs to a different character')
            return info, []
    if info['status'] != 'unresolved':
        return info, []
    root = Path(data_root).resolve()
    records = []
    for binding in info['bindings']:
        supported = {('behavior_rules', 'narrative.behavior.v1'),
                     ('personality_profile', 'narrative.dialectic.v1'),
                     ('story_evidence', 'narrative.story-index.v1')}
        if (binding['domain'], binding['schema_id']) not in supported:
            info['reason'] = 'No adapter for the bound data domain and schema'
            return info, []
        relative = binding.get('relative_path')
        if not relative:
            info['reason'] = 'A relative path inside character_data is required'
            return info, []
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path == root:
            info['reason'] = 'Data path must stay inside the project character_data directory'
            return info, []
        try:
            raw = path.read_bytes()
        except OSError:
            info['reason'] = 'Bound data file is not available'
            return info, []
        actual_hash = hashlib.sha256(raw).hexdigest()
        info.setdefault('observed_hashes', {})[binding['dataset_id']] = actual_hash
        if actual_hash.lower() != binding['content_hash'].lower():
            info['reason'] = 'Bound data content does not match its pinned hash'
            return info, []
        try:
            record = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            info['reason'] = 'Bound data is not valid UTF-8 JSON'
            return info, []
        if not isinstance(record, dict) or any(record.get(k) != binding[k]
                                               for k in ('dataset_id', 'revision', 'schema_id')):
            info['reason'] = 'Bound data identity, revision or schema does not match its reference'
            return info, []
        if binding['domain'] == 'behavior_rules':
            if not isinstance(record.get('rules'), list):
                info['reason'] = 'Behavior data must contain a rules list'
                return info, []
            if record.get('owner_id') != actor.entity_id or record.get('review_status') not in ('pending_review', 'approved'):
                info['reason'] = 'Behavior owner or review status is missing or invalid; review and rebind the package'
                return info, []
        elif binding['domain'] == 'personality_profile':
            from narrative_composer.models.character import parse_compatible_profile
            if record.get('owner_id') != actor.entity_id or record.get('review_status') not in ('pending_review', 'approved'):
                info['reason'] = 'Profile owner or review status is invalid'
                return info, []
            try:
                profile = parse_compatible_profile(record.get('profile'))
            except ValueError:
                info['reason'] = 'Character profile does not match the supported schema'
                return info, []
            names = {actor.entity_id.casefold(), actor.display_name.casefold(),
                     *(name.casefold() for name in actor.aliases)}
            if profile.character_id.casefold() not in names:
                info['reason'] = 'Profile identity does not match this character or an alias'
                return info, []
        else:
            if record.get('owner_id') != actor.entity_id or not isinstance(record.get('sources'), list):
                info['reason'] = 'Source index owner or sources are invalid'
                return info, []
            for source in record['sources']:
                if (not isinstance(source, dict) or not isinstance(source.get('file'), str)
                        or Path(source['file']).name != source['file']
                        or not isinstance(source.get('section'), str) or not source['section']
                        or not isinstance(source.get('sha256'), str)
                        or not re.fullmatch(r'[a-fA-F0-9]{64}', source['sha256'])
                        or not isinstance(source.get('references'), list)):
                    info['reason'] = 'Source index contains an invalid edition reference'
                    return info, []
                for reference in source['references']:
                    if (not isinstance(reference, dict) or not isinstance(reference.get('block_id'), str)
                            or type(reference.get('line')) is not int or reference['line'] < 1
                            or not isinstance(reference.get('line_sha256'), str)
                            or not re.fullmatch(r'[a-fA-F0-9]{64}', reference['line_sha256'])):
                        info['reason'] = 'Source index contains an invalid block reference'
                        return info, []
        records.append(record)
    info['status'] = 'resolved'
    info['datasets'] = [{'dataset_id': binding['dataset_id'], 'domain': binding['domain'],
                         'schema_id': binding['schema_id'],
                         'review_status': record.get('review_status', 'not_applicable')}
                        for binding, record in zip(info['bindings'], records)]
    domains = {item['domain'] for item in info['datasets']} | set(info.get('embedded_domains', []))
    info['capabilities'] = sorted(domains)
    info['reason'] = ('Source evidence is indexed; no personality or reaction data is attached.'
                      if domains == {'story_evidence'} else
                      'Pinned datasets loaded; profiles and source observations retain their review status.')
    return info, records
