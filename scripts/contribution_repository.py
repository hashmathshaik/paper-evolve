"""Public repository links and local PR preparation. Never pushes or submits."""
import os
import re
import shlex
from pathlib import Path
import community_edges as C
import contribution_workspace as W


def project(root=W.ROOT, environment=None):
    environment = os.environ if environment is None else environment
    path = Path(root) / 'community/project.json'
    configured = C.read_json(path).get('repository', '') if path.exists() else ''
    repository = configured or environment.get('PAPER_EVOLVE_REPOSITORY') or environment.get('GITHUB_REPOSITORY', '')
    if not isinstance(repository, str) or (repository and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository)):
        raise ValueError('Configure the public repository as OWNER/REPO, without URLs or credentials.')
    url = 'https://github.com/' + repository if repository else ''
    return {'repository': repository, 'repository_url': url,
            'fork_url': url + '/fork' if url else '', 'pulls_url': url + '/pulls' if url else ''}


def prepare_pr(destination, output=None, root=W.ROOT):
    """Export just the validated JSON and print a reviewable Git plan."""
    root = Path(root).resolve()
    destination = Path(destination)
    rows = W.check(destination)
    workspace, pack, envelope = W.load(destination)
    original = root / 'community/tasks' / (workspace['pack_id'] + '.json')
    if not original.exists() or C.digest(C.read_json(original)) != C.digest(pack):
        raise ValueError('Original committed task pack is missing or differs from the workspace.')
    contributor = envelope['submission']['contributor']['name']
    name = re.sub(r'[^a-z0-9]+', '-', contributor.lower()).strip('-')[:35] or 'contributor'
    identity = workspace['pack_id'] + '-' + name + '-' + C.digest(envelope['submission'])[:8]
    target = Path(output) if output else root / 'community/submissions' / (identity + '.json')
    if not target.is_absolute():target = root / target
    target = target.resolve()
    directory = (root / 'community/submissions').resolve()
    if not directory.is_relative_to(root) or target.parent != directory or target.suffix != '.json':
        raise ValueError('PR submissions must be JSON files directly inside community/submissions.')
    settings = project(root)
    task_versions = {(r['task_id'], r['task_sha256']) for r in envelope['submission']['decisions']}
    for existing in directory.glob('*.json'):
        document = C.read_json(existing)
        if document.get('pack') != workspace['pack_id']:continue
        overlap = task_versions.intersection((r['task_id'], r['task_sha256']) for r in document['submission']['decisions'])
        if not overlap:continue
        if C.digest(document) != C.digest(envelope) or (output is not None and existing.resolve() != target):
            raise ValueError('These tasks already appear in ' + existing.name + '; reconcile the submission instead of duplicating it.')
        target = existing.resolve()
    if target.exists():
        if C.digest(C.read_json(target)) != C.digest(envelope):raise ValueError('Output already contains a different submission.')
        result = {'decisions': len(rows), 'positive_edges': sum(r['result']['related'] for r in rows), 'published': False}
    else:
        result = W.export(destination, target, root)
    relative = target.relative_to(root).as_posix()
    # A proposed pair travels with the one-task pack that defines it; prepared packs are already committed.
    files = ([original.relative_to(root).as_posix()] if pack.get('origin') == 'contributor_proposal' else []) + [relative]
    branch = 'contribute/' + identity
    title = 'Research connections: ' + workspace['pack_id']
    body = f'''## Contribution

Pack: `{workspace['pack_id']}`
Contributor: {contributor}
Tool/model: {envelope['submission']['contributor']['tool']}
Method: {envelope['submission']['contributor']['method']}
Decisions: {result['decisions']} ({result['positive_edges']} positive proposals)

## Validation

The workspace check passed before export.
Run `python scripts/community_edges.py check` before committing.

Exact source quotes and task fingerprints were validated. This submission has
not been accepted into the graph or marked human verified. A maintainer should
review the sources before accepting it.
'''
    (destination / 'PULL_REQUEST.md').write_text(body)
    commands = [f'git switch -c {shlex.quote(branch)}', 'python scripts/community_edges.py check',
                'git add -- ' + ' '.join(shlex.quote(f) for f in files), f'git commit -m {shlex.quote(title)}',
                f'git push -u origin {shlex.quote(branch)}']
    where = settings['pulls_url'] or 'the Paper Evolve repository on GitHub'
    instructions = '# Submit from your repository clone\n\nRun these from the repository root. `origin` should be your fork.\n\n```sh\n' + '\n'.join(commands) + '\n```\n\n'
    instructions += f'Open {where}, create a pull request from your fork/branch, and use PULL_REQUEST.md as the description.\n\n'
    instructions += ('The proposed pair\'s task pack and the exported submission are staged.' if len(files) > 1 else 'Only the exported submission is staged.') + ' Workspace files stay local. A maintainer accepts the evidence separately; merging an acceptance triggers the Pages build.\n'
    (destination / 'GIT_STEPS.md').write_text(instructions)
    return {**result, 'output': relative, 'files': files, 'branch': branch, 'title': title,
            'description': str(destination / 'PULL_REQUEST.md'), 'git_steps': str(destination / 'GIT_STEPS.md'),
            'commands': commands, 'pulls_url': settings['pulls_url'], 'pushed': False, 'pull_request_created': False}
