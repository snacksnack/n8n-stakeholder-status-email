# Architecture Notes — n8n vs. Python Container, and a Possible V2

_Captured July 1, 2026, from a design discussion about where this project goes next._

## The Pyodide problem (why "Python in n8n" disappoints)

n8n's Python Code node does not run real CPython — it runs **Pyodide, a WASM build of Python in a sandbox**. Practical consequences:

- **No arbitrary packages.** Only what Pyodide bundles; no `pip install`, so no `httpx`, `pandas` beyond the bundled set, no Anthropic SDK.
- **No network calls from inside the node.** All API calls must be separate HTTP Request nodes, which is why this workflow's logic lives in JavaScript Code nodes and HTTP nodes instead.
- **Slower startup and quirky performance** vs. the JS Code node.
- **Untestable.** Code embedded in workflow JSON can't be unit-tested, linted, or reviewed like a normal codebase. (See README "Known issues" — the JSON-escaping workarounds are a symptom of the same ceiling.)

Rule of thumb: n8n's Python node is fine for small transforms; anything with dependencies, network, or logic worth testing belongs outside n8n.

## Tradeoffs: pure n8n vs. Python service on Fly.io/Cloud Run

| Dimension | n8n (current, v1) | Python container (Fly.io / Cloud Run) |
|---|---|---|
| Speed to build | Fast — visual, batteries included | Slower start; you own HTTP, auth, deploys |
| Logic complexity | Painful past a point (escaping hacks, string-built HTML) | Natural — real code, real libraries, Jinja2 templates |
| Testing | Manual runs only | pytest, CI, coverage |
| Version control | One opaque workflow JSON blob | Proper diffs, PRs, code review |
| Human-in-the-loop approval | Excellent — webhooks + Variables built in | You'd hand-roll endpoints and state |
| Scheduling / retries / cred storage | Built in | You wire it (cron, backoff, secrets manager) |
| Observability | Execution history + what we bolted on (email_log) | Real logging/metrics from day one |
| Cost | n8n Cloud ~$20/mo | Fly.io/Cloud Run free tier ≈ $0 |
| Resume signal | n8n is a JD "nice to have"; visual demo is legible | Shows software engineering depth |

Neither column wins outright — which is the point.

## Possible V2: hybrid (right tool per layer)

Keep n8n for what it's best at; move logic into a small Python service n8n calls.

```
n8n Cloud  — cron trigger, preview/approve/discard webhooks, Gmail + Slack delivery
   │  POST /report
   ▼
Python service (FastAPI, one container on Fly.io or Cloud Run)
   ├─ collectors/   jira.py, notion.py, slack.py — httpx, normalized Pydantic models
   ├─ store         SQLite/Postgres — weekly snapshots → week-over-week deltas
   ├─ narrative     Anthropic SDK — prompt gets current + prior snapshot + Slack context
   └─ renderers/    Jinja2 templates per audience: exec.html, eng.html, customer.html
```

V2 feature targets (in rough priority order):
1. **Week-over-week deltas** — cheapest win; `email_log` already captures `statusCounts`/`completionPct`, so the prompt can say "gained 15 points, cleared the auth blocker" instead of a static snapshot.
2. **Multi-audience rendering** — same data, three outputs (exec brief / eng detail / customer-safe). Flashiest portfolio demo; showcases prompt design with per-audience content rules.
3. **Qualitative signal** — fold the week's Slack channel messages into the narrative so the email explains *why* things moved, not just what moved.

## Interview framing

v1 was pure n8n; we hit its ceiling (Pyodide, untestable embedded logic, JSON-escaping workarounds) and deliberately refactored logic out while keeping n8n as the orchestration and human-in-the-loop layer. Recognizing a tool's limits and migrating deliberately is the story — worth more than either version alone.
