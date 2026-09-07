# CLAUDE.md — working notes for AI sessions and the review agent

## What this is

An n8n Cloud workflow that emails real stakeholders a weekly status report on
the AI Incident Summarizer project (RC1) every Friday at 4pm ET. Notion tasks
and this week's Jira updates feed one Code node that computes health and builds
the HTML tables; Claude writes only the executive summary; `Parse Email Content`
splices it in; Gmail sends, behind an optional preview/approval gate
(`$vars.STAKEHOLDER_EMAIL_REQUIRE_PREVIEW`). The deployable artifact is
`workflows/status-email-notification.json`; nothing here is a Python package.
`incident_summary_poller.json` is a separate, older poller workflow. Jira epic:
RC1-47. Design decisions and known n8n workarounds are in `README.md`; the eval
design is `docs/rc1-258-evals.md`.

## Layout

- `workflows/status-email-notification.json` — the workflow. Logic lives in
  JavaScript Code nodes (`Aggregate & Summarize Data`, `Parse Email Content`,
  `Format Error Message`) and HTTP Request nodes (Notion, Claude, Slack). The
  approval gate is three Webhook nodes plus two Data Tables, `pending_email`
  and `email_log`, whose table ids are committed (RC1-376). Edited in the n8n
  editor and exported; a re-import overwrites what is in n8n.
- `evals/` — `workflow.py` reads the prompt, the parser's regexes and the
  aggregate code out of the workflow JSON; `fixtures.py`; `subject.py` is the
  billed layer-2 subject on the shared `agent-evals` harness (pinned by tag in
  `requirements.txt`).
- `tests/` — layer 1, free: `test_contract.py` proves the prompt and the parser
  still agree; `test_scoring.py` checks the layer-2 scorers in both directions.
- `IMPROVEMENTS-REVIEW.md` — the June 2026 findings (P0–P3), some still open.
  `V2-ARCHITECTURE-NOTES.md` — n8n versus a Python service.

## Conventions (hold changes to these)

- **No secrets in the JSON.** The Anthropic key is `$vars.ANTHROPIC_API_KEY`,
  Slack is `$vars.SLACKBOT_WEBHOOK`, Notion is a header-auth credential, Jira
  and Gmail are n8n credentials referenced by id. A literal key, token or
  webhook URL in a node is a blocker.
- **The prompt and the parser are one contract.** `Claude — Generate Email`
  demands `SUBJECT:` then one `<div>`; `Parse Email Content` regex-extracts
  exactly that and falls back to a hardcoded subject *silently* when it misses.
  Edit them together. The tests read both out of the JSON, so a change to one
  side fails until the other follows.
- **Health is computed, never decided by the model.** `Aggregate & Summarize
  Data` holds the rules (blocked > 0 → At Risk; under 50 % with no work in
  progress → Needs Attention; else On Track). The prompt hands the level over
  verbatim and forbids the sign-off, tables and extra HTML the parser appends
  itself. `fixtures.expected_health` mirrors the rules and the test asserts the
  shipped source still contains them.
- **Claude gets scalars only.** HTML tables are built in the Code node; n8n
  expressions inside the Claude JSON body break parsing.
- **No auto-send fallback on the preview gate.** A missed Friday send is
  recoverable; an unwanted send to C-suite stakeholders is not. Discard must
  never log the email as sent (`email_log`).
- **Node names are an interface.** `evals/workflow.py` looks nodes up by name
  (`Claude — Generate Email`, `Parse Email Content`, `Aggregate & Summarize
  Data`). Renaming one fails the tests on purpose: update the eval, do not
  delete the assertion.
- **Notion and Slack go through HTTP Request nodes**, not the native nodes
  (missing operations and credential fields; see the README's known issues).
- **Python (evals and tests):** 3.12, `from __future__ import annotations`,
  ruff with line-length 100 and rules E, F, I, UP, B, SIM. Tests run offline
  with no credentials; the eval path reads no `.env` — `ANTHROPIC_API_KEY`
  comes from the process environment.

## Testing

```bash
pytest                       # layer 1 — free, CI on every push
ruff check .                 # lint
python -m evals              # layer 2 — BILLED, by hand, needs ANTHROPIC_API_KEY
python -m evals --show-prompt  # the bound prompt, free
```

## Workflow

One branch per ticket, `rc1-NNN-short-slug`; commit subjects lead with the Jira
key, `RC1-NNN: what changed`. Workflow edits are made in n8n and exported into
`workflows/`, so a PR that changes a node should say which nodes and why.
