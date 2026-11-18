# Contribute using your own API

The API route uses the same topic packs, source requirements, validation and
maintainer acceptance as Claude Code/Codex contributions. It supports the
OpenAI-compatible `/chat/completions` protocol, including compatible Qwen
endpoints. Native provider protocols are not implemented. The endpoint must
support JSON object responses and report input/output token usage.

No API requests run on the website or during a build. Keys stay in your local
process environment; the tool never reads the project's `.env` or seed-worker
credentials. Nothing runs automatically after preparing a workspace.

## Start a separate API workspace

```sh
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" \
  --tool "Your API model" --method api --output work/contributions/my-api-run
```

The runner reads your key from the variable your provider's own tools already
use, so if that is set in your terminal there is nothing more to do:

| Endpoint | Variable |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Alibaba Model Studio (Qwen) | `DASHSCOPE_API_KEY` |
| Together, Groq, DeepSeek, Mistral, Fireworks | `TOGETHER_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `FIREWORKS_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Any other endpoint | `PAPER_EVOLVE_API_KEY`, or name yours with `--api-key-env` |

A key is only sent to its own provider: an OpenAI key is never offered to a
different host. A model server on your own machine needs no key. Do not put a
key in a prompt, task file, submission, commit or web form. Check your
provider's current USD prices per million input and output tokens. Supply those
rates and your cumulative workspace allowance explicitly:

```sh
python paper_evolve.py api --workspace work/contributions/my-api-run \
  --base-url YOUR_OPENAI_COMPATIBLE_BASE_URL --model YOUR_MODEL \
  --input-rate INPUT_USD_PER_MILLION --output-rate OUTPUT_USD_PER_MILLION \
  --budget YOUR_WORKSPACE_USD_LIMIT --limit 10
```

These are placeholders, not prices or a model recommendation. You can select
a differently named variable with `--api-key-env YOUR_ENV_VARIABLE`. HTTPS is required
except for an explicitly selected loopback endpoint. Redirects are refused.

The runner reserves a conservative token allowance before each request in
`api.sqlite3`. The budget is cumulative across restarts of this workspace.
Reported usage settles the allowance; invalid output still counts as spent.
Ambiguous outcomes keep their reservation and are not automatically retried.
Rates are supplied by you, so the local estimate depends on their accuracy and
the provider honoring its output limit. Provider billing is authoritative.
Model/endpoint/rate/prompt changes require a new workspace.

You may first use `fetch` and `cite` to research papers and register excerpts;
see [RESEARCH.md](RESEARCH.md). Attachments enter the model input and exported
submission. Finish evidence preparation before the first API request; changing
evidence after inference requires a new workspace.

Only source-ready tasks are sent. Missing passages produce an explicit local
abstention without a model request. Completed decisions survive interruptions;
rerunning the same command resumes unattempted tasks. Rejected/uncertain calls
are not resent automatically. `api-status.json` records progress and reserved
cost without credentials. This ledger is separate from the maintainer's paid
seed run and does not restart it.

## Validate and submit

```sh
python paper_evolve.py check --workspace work/contributions/my-api-run
python paper_evolve.py export --workspace work/contributions/my-api-run \
  --output community/submissions/PACK_ID-your-name.json
```

Open a pull request containing the exported file in your fork of Paper Evolve.
Do not commit your workspace, ledger, credentials or modified task pack. API
decisions are proposals; neither passing validation nor running a model accepts
them into the graph. A maintainer reviews and records acceptance separately.
