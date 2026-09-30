"""Opt-in native acceptance runner. Inventory is a private JSON list of {path: d3plot}."""
import argparse
import json
import os
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--units', required=True)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--stop-file', type=Path, help='Stop cleanly between cases when this file exists')
    args = parser.parse_args()
    records = json.loads(args.inventory.read_text(encoding='utf8'))
    paths = [Path(r['path']).resolve() for r in records]
    if not paths or len(paths) > 100:
        raise ValueError('Expected 1..100 explicit result databases')
    root = Path(os.path.commonpath([str(p.parent) for p in paths]))
    service = Service(Settings(args.workspace.resolve(), args.executable.resolve(), (root,), args.timeout))
    report = json.loads(args.output.read_text(encoding='utf8')) if args.resume and args.output.exists() else []
    if args.output.exists() and not args.resume:
        raise ValueError('Report exists; use --resume or a new output')
    for i, source in enumerate(paths):
        if args.stop_file and args.stop_file.exists():
            print('Stopped at case boundary; existing evidence preserved.', flush=True)
            return
        if any(r['source'] == str(source) for r in report):
            continue
        result = service.native_postprocess_case(str(source), args.units)
        report.append({'source': str(source), 'case_index': i+1, 'result': result})
        atomic_json(args.output, report)
        print(f'{i+1}/{len(paths)} {source.parent.parent.name}: {result["status"]}; checks={len(result.get("checks", []))}', flush=True)
    print('Completed report:', args.output, flush=True)


if __name__ == '__main__':
    main()
