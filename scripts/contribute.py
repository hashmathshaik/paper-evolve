"""Two entry points, one evidence format: contributor agents and opt-in APIs."""
import argparse
import json
import re
from pathlib import Path
import contribution_workspace as W


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    ls = commands.add_parser('list', help='List available topic packs.')
    ls.add_argument('--topic', default='')
    ls.add_argument('--json', action='store_true')
    start = commands.add_parser('start', help='Prepare a frozen pack, prompt and submission workspace.')
    start.add_argument('--pack', required=True)
    start.add_argument('--name', required=True)
    start.add_argument('--tool', required=True, help='Actual agent/model version, or the planned API model.')
    start.add_argument('--method', choices=['assistant', 'api', 'manual', 'local_model'], default='assistant')
    start.add_argument('--limit', type=int, default=10)
    start.add_argument('--output', type=Path)
    check = commands.add_parser('check', help='Validate a completed contribution.')
    check.add_argument('--workspace', type=Path, required=True)
    export = commands.add_parser('export', help='Prepare validated JSON for a pull request; never publishes.')
    export.add_argument('--workspace', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    pr = commands.add_parser('pr', help='Export a submission and prepare Git/PR instructions without pushing.')
    pr.add_argument('--workspace', type=Path, required=True)
    pr.add_argument('--output', type=Path)
    fetch = commands.add_parser('fetch', help='Download and extract the full papers for a selected task.')
    fetch.add_argument('--workspace', type=Path, required=True)
    fetch.add_argument('--task', required=True)
    fetch.add_argument('--side', choices=['a','b','both'], default='both')
    fetch.add_argument('--url', help='Official PDF or matching open-access version for one side.')
    fetch.add_argument('--file', type=Path, help='Import a PDF already downloaded by your agent; --url records its public source.')
    cite = commands.add_parser('cite', help='Attach an exact page excerpt from a downloaded PDF.')
    cite.add_argument('--workspace', type=Path, required=True)
    cite.add_argument('--task', required=True)
    cite.add_argument('--side', choices=['a','b'], required=True)
    cite.add_argument('--page', type=int, required=True)
    cite.add_argument('--kind', choices=['passage','citation'], default='passage')
    cite.add_argument('--quote-file', type=Path, required=True)
    api = commands.add_parser('api', help='Opt in to API requests using your own key, rates and budget.')
    api.add_argument('--workspace', type=Path, required=True)
    api.add_argument('--base-url', required=True, help='OpenAI-compatible API base URL ending in /v1.')
    api.add_argument('--model', required=True)
    api.add_argument('--api-key-env', default='PAPER_EVOLVE_API_KEY')
    api.add_argument('--input-rate', type=float, required=True, help='Current USD price per million input tokens.')
    api.add_argument('--output-rate', type=float, required=True, help='Current USD price per million output tokens.')
    api.add_argument('--budget', type=float, required=True, help='Cumulative workspace allowance in USD, including holds.')
    api.add_argument('--max-output', type=int, default=2048)
    api.add_argument('--limit', type=int, default=10)
    args = ap.parse_args()
    try:
        if args.command == 'list':
            packs = [p for p in W.manifest(refresh=True)['packs'] if args.topic.casefold() in (p.get('topic', '') + ' ' + p.get('area', '')).casefold()]
            if args.json:print(json.dumps(packs, ensure_ascii=False))
            else:
                for p in packs:
                    print(f"{p['id']}\t{p.get('available_tasks', p['tasks'])} available\t{p.get('topic', 'Starter collection')}")
        elif args.command == 'start':
            path = W.resolve_pack(args.pack)
            out = args.output or W.ROOT / 'work/contributions' / path.stem
            workspace = W.prepare(path, out, args.name, args.tool, args.method, args.limit)
            print(f"Prepared {len(workspace['selected_task_ids'])} tasks in {out}\nGive your agent {out / 'PROMPT.md'}")
            print(f'Validate: python paper_evolve.py check --workspace "{out}"')
            print(f'Prepare pull request: python paper_evolve.py pr --workspace "{out}"')
        elif args.command == 'check':
            rows = W.check(args.workspace)
            print(json.dumps({'validated': len(rows), 'positive_edges': sum(r['result']['related'] for r in rows), 'published': False}))
        elif args.command == 'export':
            print(json.dumps(W.export(args.workspace, args.output)))
        elif args.command == 'pr':
            from contribution_repository import prepare_pr
            print(json.dumps(prepare_pr(args.workspace, args.output)))
        elif args.command == 'fetch':
            from contribution_sources import fetch_papers
            print(json.dumps(fetch_papers(args.workspace,args.task,args.side,args.url,args.file)))
        elif args.command == 'cite':
            from contribution_sources import cite
            print(json.dumps(cite(args.workspace,args.task,args.side,args.page,args.kind,args.quote_file)))
        else:
            from contribution_api import run
            print(json.dumps(run(args.workspace, args.base_url, args.model, args.api_key_env, args.input_rate,
                                 args.output_rate, args.budget, args.max_output, args.limit)))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        ap.exit(1, f'Contribution failed: {exc}\n')
