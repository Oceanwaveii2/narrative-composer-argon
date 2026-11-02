"""Integrated project analysis, portable editor demo, and explicit stage reporting."""
import argparse
import json
from pathlib import Path
import shutil

from narrative_composer.graph.registry import load_registry
from narrative_composer.store import build_store
from narrative_composer.workspace import project_report


def analyze(script, manifest, entity_dir, canon='story', event='challenge'):
    store = build_store(Path(script), Path(manifest), registry=load_registry(Path(entity_dir)), canon=canon)
    return store, project_report(store, event)


def create_demo(destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Demo destination already exists; choose a new folder to preserve authored work')
    source = Path(__file__).parent / 'tests' / 'fixtures' / 'recovery_project'
    shutil.copytree(source, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', help='Create a new isolated two-character project directory')
    parser.add_argument('--script')
    parser.add_argument('--manifest')
    parser.add_argument('--entity-dir')
    parser.add_argument('--canon', default='recovery')
    parser.add_argument('--event', default='challenge')
    parser.add_argument('--out', help='Write the integrated analysis report')
    args = parser.parse_args()
    if args.demo:
        root = create_demo(args.demo)
        args.script, args.manifest, args.entity_dir = root/'story.md', root/'manifest.json', root/'characters'
    if not all((args.script, args.manifest, args.entity_dir)):
        parser.error('Supply --demo or all of --script, --manifest, --entity-dir')
    _, report = analyze(args.script, args.manifest, args.entity_dir, args.canon, args.event)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
