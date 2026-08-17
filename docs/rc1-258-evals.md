# Evaluating the status-email workflow (RC1-258)

The workflow runs in n8n Cloud and emails real stakeholders every Friday. Two
layers test it, split by what they cost.

## Layer 1 — the prompt/parser contract (free, gates)

`pytest`. No credentials, no tokens, runs on every push.

Three nodes form a chain, and the middle two have a contract nothing declared:

```
Aggregate & Summarize Data   computes health and counts — deterministic
  → Claude — Generate Email  prompt demands `SUBJECT:` then one <div>
  → Parse Email Content      regex-extracts exactly that shape
```

**`Parse Email Content` falls back to a hardcoded subject when its regex
misses.** So editing the prompt's output format without updating the parser
raises no error: a stakeholder gets an email with a stale generic subject and
the real subject line buried in the body.

Everything is read out of `workflows/status-email-notification.json` at test
time, including the parser's own regexes. A test asserting against a *copy* of
the prompt would pass forever, including after someone changed the real one.

Verified by doing it, in both directions:

| Edit | Result |
|---|---|
| Prompt: `SUBJECT:` → `RE:`, parser untouched | 3 tests fail |
| Parser: subject regex stops terminating on `<`, prompt untouched | 1 test fails |

## Layer 2 — prompt goldens (billed, by hand)

```bash
export ANTHROPIC_API_KEY=...
python -m evals                  # all four fixtures
python -m evals --case blocked   # one
python -m evals --show-prompt    # the bound prompt, free
```

Binds a fixture into the committed prompt and calls the Messages API with the
model the workflow pins. No n8n runtime, no Notion, no Jira, no Gmail — and
nothing is emailed.

The run/record/exit plumbing is the shared
[`agent-evals`](https://github.com/snacksnack/agent-evals) harness (RC1-262);
what lives here is only this repo's subject and fixtures. `ANTHROPIC_API_KEY`
is read from the process environment — this repo's eval path reads no `.env`.
Records land in the shared store when `EVAL_DATABASE_URL` is set (else a local
gitignored `eval-runs/runs.jsonl`), and render to the
[quality trend page](https://snacksnack.github.io/agent-evals/) — see the
library's
[runbook](https://github.com/snacksnack/agent-evals/blob/main/docs/measuring.md).

Four fixtures cover the three health states and the boundary between them. The
boundary case is 49% complete *with work in progress*: below the 50% threshold
and still On Track, because the Needs Attention branch also requires
`inProgress === 0`. That is the state a reader of the prompt is most likely to
get wrong, which is why it is frozen.

The strongest check is `parses-through-the-shipped-parser`: it runs the real
model's real output through the regexes read out of `Parse Email Content`.
Layer 1 proves the two agree in principle; this proves the model actually
produces the format.

## What is deliberately not tested

**End-to-end execution through the webhook trigger.** It needs a test variant of
the workflow with fixture-injecting nodes so it does not hit live Notion, Jira
and Gmail, plus a hosted n8n instance in CI. The cost is real and the coverage
gained is mostly n8n plumbing rather than output quality.

Revisit if a bug appears that layers 1 and 2 could not have caught. That is the
evidence that would justify it; absent that, this is a deferral rather than an
oversight.
