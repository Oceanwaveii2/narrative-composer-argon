"""Source-scoped, unapproved cast candidates for author review."""
import hashlib

from narrative_composer.graph.discover import discover
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.models.ast_nodes import ASTNodeType
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.store import registry_from_store


def discover_cast(store, text):
    registry = registry_from_store(store)
    elements = FountainParser.parse(text)
    result = discover(elements, StoryGraph.from_registry(registry), store.meta['canon'], 'cast_review')
    blocks = store.of_kind('block')
    candidates = []
    for actor in result.new_entities:
        aliases = {name.upper() for name in actor.get('aliases', [])}
        line = actor.get('attributes', {}).get('first_seen_line') or 0
        if not line:
            for element in elements:
                if element.node_type == ASTNodeType.CHARACTER:
                    cue = element.content.upper()
                    for suffix in ("(CONT'D)", '(O.S.)', '(V.O.)'):
                        cue = cue.replace(suffix, '').strip()
                    if cue in aliases:
                        line = element.line_number
                        break
        block = next((item for item in blocks if item.data.get('line') == line), None)
        evidence = {'source_file': str(store.meta['source']).replace('\\', '/').split('/')[-1],
                    'source_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    'line': line or None, 'block_id': block.id if block else None,
                    'evidence_hash': hashlib.sha256(block.data.get('text', '').encode('utf-8')).hexdigest() if block else None}
        candidates.append({'entity_id': actor['entity_id'], 'display_name': actor['display_name'],
                           'evidence': evidence, 'candidate': actor,
                           'status': 'unreviewed heuristic; not an approved character'})
    return candidates
