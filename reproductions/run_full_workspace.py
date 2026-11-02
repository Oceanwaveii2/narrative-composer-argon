"""Run complete source texts through the existing graph/document analysis pipeline."""
import argparse
import contextlib
import hashlib
import html
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_pipeline import run_pipeline
from narrative_composer.editor import timeline_sections
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.viewer import render_viewer
from narrative_composer.store import build_store, to_text, document_from_store
from narrative_composer.compiler.reader_renderer import GENERIC_THEME, render_reader
from narrative_composer.compiler.document import BlockRole
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.linter.html_feedback_loop import HTMLFeedbackLoopVerifier
from narrative_composer.workspace import project_report


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    workspace, output = args.workspace.resolve(), args.out.resolve()
    if output.exists() or output.is_relative_to(workspace):
        raise ValueError('Use a new output folder outside the source workspace')
    sections = timeline_sections(workspace / 'timeline.json')
    registry = load_registry(workspace / 'characters')
    graph = StoryGraph.from_registry(registry)
    tracked = {workspace / 'timeline.json'}
    for section in sections:
        tracked.update((section['story'], section['manifest']))
    tracked.update((workspace / 'characters').rglob('*.json'))
    provenance = workspace / 'SOURCE_PROVENANCE.json'
    if provenance.exists():
        origin = json.loads(provenance.read_text(encoding='utf-8'))
        tracked.add(Path(origin['original_story_path']))
    before = {str(path): digest(path) for path in tracked}
    output.mkdir(parents=True)
    results = []
    for section in sections:
        folder = output / section['id']
        folder.mkdir()
        text = section['story'].read_bytes().decode('utf-8')
        with (folder / 'pipeline.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
            run_pipeline(str(section['story']), section['canon'], 'story', str(folder),
                         str(folder / 'reader.html'), str(section['manifest']), str(workspace / 'characters'))
        store = build_store(section['story'], section['manifest'], registry=registry,
                            canon=section['canon'], text=text, use_cache=False)
        if to_text(store) != text:
            raise ValueError('Text projection changed: ' + section['id'])
        (folder / 'nodes.json').write_text(json.dumps(store.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        report = project_report(store)
        document = document_from_store(store)
        theme = replace(GENERIC_THEME, page_title=section['id'], graph_href='story.viewer.html',
                        verified_note='Analysis output; author review required')
        (folder / 'reader.html').write_text(render_reader(document, theme), encoding='utf-8')
        audit = HTMLFeedbackLoopVerifier.audit_html(folder / 'reader.html')
        (folder / 'reader.audit.json').write_text(json.dumps(asdict(audit), indent=2, ensure_ascii=False), encoding='utf-8')
        prose = []
        for block in document.blocks:
            if block.role == BlockRole.ACTION:
                diagnostic = ProseDiagnosticsAnalyzer.analyze(block.text)
                prose.append({'block_id': block.id, 'line': block.line,
                              'diagnostics': diagnostic.model_dump(mode='json')})
        (folder / 'prose.diagnostics.json').write_text(json.dumps(prose, indent=2, ensure_ascii=False), encoding='utf-8')
        graph_report = json.loads((folder / 'story.report.json').read_text(encoding='utf-8'))
        actors = []
        for identity, actor in registry.items():
            if actor.canons and section['canon'] not in actor.canons:
                continue
            filename = 'character_' + identity + '.html'
            render_viewer(store.meta['run_graph'], graph_report, folder / filename, graph=graph,
                          data_root=workspace / 'character_data', initial_entity=identity, initial_mode='definitions')
            actors.append({'id': identity, 'file': filename, 'forms': len(actor.states)})
        result = {'id': section['id'], 'source_sha256': digest(section['story']),
                  'source_bytes': len(text.encode('utf-8')), 'blocks': len(document.blocks),
                  'nodes': len(store.nodes), 'diagnostics': dict(Counter(d['severity'] for d in report['diagnostics'])),
                  'coverage': report['coverage'], 'characters': actors,
                  'action_blocks_analyzed': len(prose),
                  'flagged_action_blocks': sum(bool(p['diagnostics']['warnings']) for p in prose),
                  'reader_dom_violations': sum(v.stage == 'DOM_INTEGRITY' for v in audit.violations),
                  'character_data_status': dict(Counter(r['data_input']['status'] for r in report['reactions'])),
                  'composition': 'not run: existing authored manuscript; select a reviewed beat to generate',
                  'model_conditioning': 'not run on complete text; diagnostics cover all action blocks',
                  'text_projection_exact': True}
        results.append(result)
        print('Processed', section['id'], 'blocks', len(document.blocks), 'nodes', len(store.nodes), flush=True)
    after = {str(path): digest(path) for path in tracked}
    summary = {'sections': results, 'source_files_unchanged': before == after,
               'source_hashes': before, 'variants_are_separate': True,
               'note': 'The master overlaps the section editions; do not sum these as unique story text.'}
    (output / 'run.report.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    rows = []
    for result in results:
        identity = html.escape(result['id'])
        links = ' '.join('<a href="'+identity+'/'+html.escape(a['file'])+'">'+html.escape(a['id'])+'</a>' for a in result['characters'])
        rows.append(f'<tr><td>{identity}</td><td>{result["blocks"]}</td><td>{html.escape(str(result["diagnostics"]))}</td><td><a href="{identity}/reader.html">Reader</a> · <a href="{identity}/story.viewer.html">Graph</a> · <a href="{identity}/project.report.json">Report</a> · <a href="{identity}/prose.diagnostics.json">Prose diagnostics</a><br>{links}</td></tr>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Full-text processing results</title><style>body{background:#101925;color:#dce6f1;font:16px/1.5 system-ui;max-width:1400px;margin:40px auto;padding:20px}a{color:#9ee8d2}td,th{padding:12px;border:1px solid #405467;text-align:left}table{border-collapse:collapse;width:100%}</style><h1>Full-text processing results</h1><p>Complete master and separate timeline editions. Source files unchanged: '+str(before == after)+'.</p><p>Readers, graphs, actor/form ports, node snapshots, reaction-data status, prose diagnostics and reader audits were generated. Model rewrites and new beat generation were not run on the full manuscripts. Graph findings require review; missing personality data is not invented.</p><p><a href="run.report.json">Combined machine-readable report</a></p><table><tr><th>Edition</th><th>Blocks</th><th>Diagnostics</th><th>Outputs and character graphs</th></tr>'+''.join(rows)+'</table></html>'
    (output / 'index.html').write_text(page, encoding='utf-8')
    if before != after:
        raise ValueError('A source hash changed during processing')
    print('Complete:', output / 'index.html', flush=True)


if __name__ == '__main__':
    main()
