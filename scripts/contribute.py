"""Two entry points, one evidence format: contributor agents and opt-in APIs."""
import argparse
import json
import subprocess
from pathlib import Path
import contribution_workspace as W


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    ls = commands.add_parser('list', help='List available topic packs.')
    ls.add_argument('--topic', default='')
    ls.add_argument('--pack', help='Show the paper pairs inside one pack.')
    find = commands.add_parser('find', help='Search the collection for a paper by title words, URL or ID.')
    find.add_argument('query')
    propose = commands.add_parser('propose', help='Create a task for a pair of papers you choose.')
    propose.add_argument('--earlier', required=True, help='Title, source URL or ID of the earlier paper.')
    propose.add_argument('--later', required=True, help='Title, source URL or ID of the later paper.')
    commands.add_parser('topics', help='List the topics a new paper can be filed under.')
    venue = commands.add_parser('add-venue', help='Register a conference or journal so its papers can be added.')
    venue.add_argument('--id', required=True, help='Short lowercase id, for example cvpr.')
    venue.add_argument('--name', required=True, help='Display name, for example CVPR.')
    venue.add_argument('--host', action='append', required=True, help='Official host of its paper pages; repeatable.')
    papers = commands.add_parser('add-papers', help='Validate a list of new papers and prepare it for a pull request.')
    papers.add_argument('--file', type=Path, required=True, help='JSON list of papers; see community/PAPERS.md.')
    papers.add_argument('--name', required=True)
    papers.add_argument('--tool', required=True, help='Actual agent/model version that gathered the papers, or "manual".')
    run = commands.add_parser('run', help='Let Claude Code or Codex review packs with one command; never pushes.')
    run.add_argument('--agent', choices=['claude', 'codex'], default='claude')
    run.add_argument('--name', required=True)
    run.add_argument('--pack', action='append', default=[], help='Pack ID; repeat for several.')
    run.add_argument('--count', type=int, default=0, help='Also take the next N packs that still have open tasks.')
    run.add_argument('--topic', default='', help='Limit --count to matching topics or areas.')
    run.add_argument('--earlier', help='With --later: propose this pair and review it.')
    run.add_argument('--later')
    run.add_argument('--task', action='append', help='Review only this task ID; repeatable.')
    run.add_argument('--limit', type=int, default=10)
    run.add_argument('--model', help='Model name passed to the agent; otherwise its default.')
    run.add_argument('--agent-command', help='Another agent CLI, with {prompt} and {workspace} placeholders.')
    run.add_argument('--timeout', type=int, default=45, help='Minutes allowed per agent run.')
    run.add_argument('--no-pr', action='store_true', help='Stop after validation; do not export submissions.')
    ls.add_argument('--json', action='store_true')
    start = commands.add_parser('start', help='Prepare a frozen pack, prompt and submission workspace.')
    start.add_argument('--pack', required=True)
    start.add_argument('--name', required=True)
    start.add_argument('--tool', required=True, help='Actual agent/model version, or the planned API model.')
    start.add_argument('--method', choices=['assistant', 'api', 'manual', 'local_model'], default='assistant')
    start.add_argument('--limit', type=int, default=10)
    start.add_argument('--task', action='append', help='Take only this task ID; repeatable. See: list --pack PACK_ID')
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
    api.add_argument('--api-key-env', help="Variable holding your key. Default: your provider's usual one, such as OPENAI_API_KEY.")
    api.add_argument('--input-rate', type=float, required=True, help='Current USD price per million input tokens.')
    api.add_argument('--output-rate', type=float, required=True, help='Current USD price per million output tokens.')
    api.add_argument('--budget', type=float, required=True, help='Cumulative workspace allowance in USD, including holds.')
    api.add_argument('--max-output', type=int, default=2048)
    api.add_argument('--limit', type=int, default=10)
    args = ap.parse_args()
    try:
        if args.command == 'list' and args.pack:
            import community_edges as C
            pack = C.read_json(W.resolve_pack(args.pack))
            entry = next((p for p in W.manifest(refresh=True)['packs'] if p['id'] == args.pack), None)
            is_open = set(entry['available_task_ids']) if entry else set(W.available_tasks(args.pack, pack))
            rows = [{'task': t['id'], 'open': t['id'] in is_open, 'sources': t['state'].get('source_evidence', {}).get('status', 'none'),
                     'earlier': f"{t['state']['paper_a']['year']} {t['state']['paper_a']['title']}",
                     'later': f"{t['state']['paper_b']['year']} {t['state']['paper_b']['title']}"} for t in pack['tasks']]
            if args.json:print(json.dumps(rows, ensure_ascii=False))
            else:
                for r in rows:
                    print(f"{r['task']}\t{'open' if r['open'] else 'taken'}\t{r['earlier']}\n\t\t-> {r['later']}")
        elif args.command == 'find':
            import contribution_proposals as P
            records, raw = P.corpus()
            hits = P.find(args.query, records, raw)
            for i in hits[:20]:
                print(f"{records[i]['id']}\t{records[i]['year']}\t{records[i]['title']}")
            print(f'{len(hits)} match(es)' + ('; showing 20. Add more title words.' if len(hits) > 20 else ''))
        elif args.command == 'topics':
            import contribution_papers as N
            for topic, area in sorted(N.topics().items(), key=lambda item: (item[1], item[0])):
                print(f'{area}\t{topic}')
        elif args.command == 'add-venue':
            import contribution_papers as N
            print(json.dumps(N.add_venue(args.id, args.name, args.host)))
        elif args.command == 'add-papers':
            import contribution_papers as N
            print(json.dumps(N.submit(args.file, args.name, args.tool), ensure_ascii=False, indent=1))
        elif args.command == 'propose':
            import contribution_proposals as P
            made = P.propose(args.earlier, args.later)
            print(f"Created {made['path']}\n  {made['earlier']['year']} {made['earlier']['title']}\n  -> {made['later']['year']} {made['later']['title']}")
            print(f"Review it yourself: python paper_evolve.py start --pack {made['pack']} --name \"Your name\" --tool \"Your agent / model\"")
            print(f"Or in one command:  python paper_evolve.py run --pack {made['pack']} --name \"Your name\"")
        elif args.command == 'run':
            import contribution_agent as G
            packs = list(args.pack)
            if bool(args.earlier) != bool(args.later):raise ValueError('Give both --earlier and --later to propose a pair.')
            if args.earlier:
                import contribution_proposals as P
                packs.append(P.propose(args.earlier, args.later)['pack'])
            if args.count:packs += [p for p in G.next_packs(args.count, args.topic) if p not in packs]
            if not packs:raise ValueError('Choose --pack, --count or an --earlier/--later pair.')
            summary = G.run(packs, args.name, args.agent, args.model, args.limit, args.task, args.agent_command,
                            args.timeout, prepare_pr=not args.no_pr)
            print(json.dumps(summary, ensure_ascii=False, indent=1))
            if any('error' in row for row in summary['packs']):ap.exit(1, 'Some packs were not completed; rerun the same command to resume.\n')
        elif args.command == 'list':
            packs = [p for p in W.manifest(refresh=True)['packs'] if args.topic.casefold() in (p.get('topic', '') + ' ' + p.get('area', '')).casefold()]
            if args.json:print(json.dumps(packs, ensure_ascii=False))
            else:
                for p in packs:
                    print(f"{p['id']}\t{p.get('available_tasks', p['tasks'])} available\t{p.get('topic', 'Starter collection')}")
        elif args.command == 'start':
            path = W.resolve_pack(args.pack)
            out = args.output or W.ROOT / 'work/contributions' / path.stem
            workspace = W.prepare(path, out, args.name, args.tool, args.method, args.limit, only=args.task)
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
    except ModuleNotFoundError:
        ap.exit(1, 'This command needs a clone of the repository; a downloaded kit does not include it.\n')
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        ap.exit(1, f'Contribution failed: {exc}\n')
