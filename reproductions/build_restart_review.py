"""Summarize an existing timeline graph and scoped provider audit without rewriting text."""
import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', required=True, type=Path)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--focused', required=True, type=Path)
    args = parser.parse_args()
    full = args.full.resolve()
    combined = read(full / 'run.report.json')
    grouped = {}
    table_rows = []
    for section in combined['sections']:
        identity = section['id']
        report = read(full / identity / 'project.report.json')
        groups = defaultdict(list)
        for item in report['diagnostics']:
            if item['severity'] == 'ERROR':
                groups[(item['rule_id'], item['message'])].append(item['line'])
        grouped[identity] = [{'rule': key[0], 'message': key[1], 'count': len(lines),
                              'lines': sorted(lines)}
                             for key, lines in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))]
        rules = Counter({})
        for item in grouped[identity]:
            rules[item['rule']] += item['count']
        table_rows.append({'edition': identity, 'errors': sum(rules.values()), 'rules': dict(rules)})
    graph_report = {'editions': table_rows, 'groups': grouped,
        'source_files_unchanged': combined['source_files_unchanged'],
        'interpretation': 'Findings are observations and unresolved validation, not proof that the manuscript is wrong.'}
    (full / 'graph_review.json').write_text(json.dumps(graph_report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['# Graph review', '',
        'Source and edition identities remain separate. The master overlaps several section editions, so counts are not additive.', '',
        '| Edition | Errors | Rule counts |', '|---|---:|---|']
    lines += [f"| {row['edition']} | {row['errors']} | {', '.join(f'{k}: {v}' for k, v in row['rules'].items()) or 'None'} |"
              for row in table_rows]
    lines += ['', '## Master findings grouped for review', '',
        'G2 means a speaker cue asserts a different form from the current accepted graph state. G8 means an observed form lacks an approved direct transition and causal trigger. Neither proves the author made a mistake. The same unresolved state can generate many repeated cues.', '']
    for item in grouped['gemini_master']:
        sample = ', '.join(str(i) for i in item['lines'][:12])
        if len(item['lines']) > 12:
            sample += ', …'
        lines.append(f"- **{item['rule']} ({item['count']})** {item['message']} Lines: {sample}.")
    lines += ['', '## How to review', '',
        'Open the matching edition in the editor and inspect the source block and graph. Accept a correct observed form only after checking its source. A reviewed observation does not approve the transition cause; review causal evidence separately. Do not create transitions just to erase errors.', '',
        'The grouped Rainee form entry patterns no longer treat the source description of forms folding together as a new entry. This removed one false G8 finding. Further findings are not automatically approved.', '',
        'All seven actor ports load source indexes. Only Rainee and Haley have existing personality profiles, both pending review. No actor has a supplied authored behavior-rule package. A loaded source index is not a personality model.', '']
    (full / 'GRAPH_REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
    rows_html = ''.join('<tr><td><a href="'+html.escape(x['edition'])+'/story.viewer.html">'+html.escape(x['edition'])+'</a></td><td>'+str(x['errors'])+'</td><td>'+html.escape(', '.join(f'{k}: {v}' for k,v in x['rules'].items()) or 'None')+'</td></tr>' for x in table_rows)
    groups_html = ''.join('<li><b>'+html.escape(x['rule'])+' ('+str(x['count'])+')</b> '+html.escape(x['message'])+' Lines: '+html.escape(', '.join(map(str,x['lines'][:12])) + (', …' if len(x['lines'])>12 else ''))+'.</li>' for x in grouped['gemini_master'])
    style = 'body{background:#101925;color:#dce6f1;font:16px/1.55 system-ui;max-width:1250px;margin:40px auto;padding:20px}a{color:#9ee8d2}td,th{padding:10px;border:1px solid #405467;text-align:left}table{border-collapse:collapse;width:100%}li{margin:10px 0}blockquote{border-left:3px solid #70bea9;padding-left:16px;margin-left:0;white-space:pre-wrap}details{border:1px solid #405467;padding:14px;margin:12px 0}summary{cursor:pointer;font-weight:bold}'
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Graph review</title><style>'+style+'</style><h1>Graph review</h1><p>These findings need source review. Repeated state-cue mismatches and unverified transition causes do not prove the manuscript is wrong. The master overlaps several section editions; do not add the counts together.</p><table><tr><th>Edition / graph</th><th>Errors</th><th>Rule counts</th></tr>'+rows_html+'</table><h2>Master findings</h2><ul>'+groups_html+'</ul><p>Use Nodes &amp; diagnostics to review each source observation; accepting a form does not approve its causal transition. The Rainee grouped-form return was corrected as an entry-pattern false positive. Source indexes are lexical candidates; two existing profiles remain pending review and behavior packages are missing.</p><p><a href="GRAPH_REVIEW.md">Text version</a> · <a href="index.html">All outputs</a></p></html>'
    (full / 'graph_review.html').write_text(page, encoding='utf-8')

    proposals = read(args.audit / 'provider_proposals.json')
    retry = read(args.focused / 'conditioner_proposals.json')
    blocks = []
    for item in proposals + retry:
        retry_item = item in retry
        status = ('New attempt after subject-check fix' if retry_item else
                  'Mechanically eligible; author review required' if item.get('eligible') else 'Held by the earlier subject check')
        blocks.append('<details><summary>'+html.escape(item['section'])+' · line '+str(item['source_line'])+' — '+html.escape(status)+'</summary><p>Original</p><blockquote>'+html.escape(item.get('original',''))+'</blockquote><p>Venice proposal</p><blockquote>'+html.escape(item.get('proposed',''))+'</blockquote></details>')
    proposal_page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Venice proposals</title><style>'+style+'</style><h1>Venice proposals for review</h1><p>Seven individually reviewed non-explicit source passages were sent to Venice. The final card is a fresh attempt after correcting a false subject-check rejection. No proposal was applied. Passing a mechanical check does not mean the rewrite preserved the author’s meaning; some candidates add details or alter an action, so review each original and proposed passage carefully.</p>'+''.join(blocks)+'<p><a href="index.html">All outputs</a></p></html>'
    (full / 'venice_proposals.html').write_text(proposal_page, encoding='utf-8')
    index = full / 'index.html'
    body = index.read_text(encoding='utf-8')
    marker = '<p><a href="run.report.json">Combined machine-readable report</a></p>'
    extra = '<p><a href="graph_review.html">Graph error review</a> · <a href="venice_proposals.html">Venice proposal review</a></p>'
    if marker in body and extra not in body:
        index.write_text(body.replace(marker, marker + extra), encoding='utf-8')
    print('Graph and Venice review pages created in', full)


if __name__ == '__main__':
    main()
