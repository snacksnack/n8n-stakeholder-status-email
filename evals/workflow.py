"""Read the prompt and the parser out of the committed workflow JSON (RC1-258).

The workflow is the source of truth and it is version-controlled, so the prompt
is an extractable, diffable artifact even though it lives inside an n8n node.
Nothing here runs n8n.

## Why this module exists rather than a copy of the prompt

A test that asserts against a *copy* of the prompt passes forever, including
after someone edits the real one. Everything is read from
`workflows/status-email-notification.json` at test time, so the contract tests
are about the shipped workflow or they are about nothing.

## The coupling that motivates all of this

Three nodes form a chain, and the middle two have an undeclared contract:

    Aggregate & Summarize Data  (computes health, counts — deterministic)
      -> Claude — Generate Email  (prompt demands `SUBJECT:` then one <div>)
      -> Parse Email Content      (regex-extracts exactly that shape)

`Parse Email Content` falls back to a hardcoded subject when its regex misses.
So if the prompt's output format is edited and the parser is not, nothing
errors: a stakeholder gets an email with a stale generic subject and the real
subject line embedded in the body. That is the failure this repo had no way to
catch, and layer 1 catches it for free.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / "workflows" / "status-email-notification.json"
)

PROMPT_NODE = "Claude — Generate Email"
PARSER_NODE = "Parse Email Content"
AGGREGATE_NODE = "Aggregate & Summarize Data"


@cache
def workflow() -> dict:
    return json.loads(WORKFLOW_PATH.read_text())


@cache
def node(name: str) -> dict:
    for candidate in workflow().get("nodes", []):
        if candidate.get("name") == name:
            return candidate
    raise KeyError(
        f"no node named {name!r} in {WORKFLOW_PATH.name}. The workflow was renamed or "
        "restructured — update the eval rather than deleting the assertion."
    )


@cache
def request_body() -> str:
    """The raw `jsonBody` of the Claude request node, n8n expression and all.

    Returned as text rather than parsed JSON on purpose: it is not valid JSON.
    It opens with `=` (n8n's expression marker) and embeds `{{ $json.x }}`
    placeholders, so parsing it would mean stripping exactly the things the
    contract is about.
    """
    return str(node(PROMPT_NODE)["parameters"]["jsonBody"])


@cache
def prompt_text() -> str:
    """The user-turn content — the prompt itself, placeholders intact."""
    body = request_body()
    match = re.search(r'"content"\s*:\s*"(.*?)"\s*\n?\s*\}', body, re.DOTALL)
    if match is None:
        raise ValueError(
            "could not find the user-turn content in the Claude node's jsonBody. "
            "The request shape changed; the contract tests cannot speak for it."
        )
    return match.group(1)


@cache
def parser_code() -> str:
    return str(node(PARSER_NODE)["parameters"]["jsCode"])


@cache
def aggregate_code() -> str:
    return str(node(AGGREGATE_NODE)["parameters"]["jsCode"])


@cache
def model() -> str:
    match = re.search(r'"model"\s*:\s*"([^"]+)"', request_body())
    return match.group(1) if match else ""


#: Placeholders the prompt interpolates from the Aggregate node. Extracted
#: rather than listed, so a new one cannot be added without the fixtures
#: noticing — `tests/test_contract.py` asserts every fixture supplies them all.
@cache
def placeholders() -> tuple[str, ...]:
    return tuple(sorted(set(re.findall(r"\{\{\s*\$json\.(\w+)\s*\}\}", prompt_text()))))


def bind(values: dict[str, object]) -> str:
    """Substitute `{{ $json.x }}` placeholders, the way n8n would.

    Raises on a placeholder with no value rather than leaving it in the prompt:
    a literal `{{ $json.health }}` reaching the model is a bug that would
    otherwise show up as a mysteriously bad summary.
    """
    missing = [name for name in placeholders() if name not in values]
    if missing:
        raise KeyError(f"no value supplied for: {', '.join(missing)}")

    def _sub(match: re.Match[str]) -> str:
        return str(values[match.group(1)])

    return re.sub(r"\{\{\s*\$json\.(\w+)\s*\}\}", _sub, prompt_text())


# --- the parser's own regexes, read from its source -----------------------
#
# Applied in Python against a response built to the prompt's stated format.
# Reading them out of the shipped JavaScript is the whole point: a Python
# re-implementation would be a second thing to keep in sync, and it would go
# stale silently — which is the exact failure mode under test.

_SUBJECT_RE = re.compile(r"text\.match\(/(?P<pattern>.+?)/\)")
_STRIP_RE = re.compile(r"text\.replace\(/(?P<pattern>SUBJECT:.+?)/,\s*''\)")


def _js_to_python(pattern: str) -> str:
    """Translate the JS regex bodies used here into Python equivalents.

    Only what these two patterns need: JS `(?=...)` lookahead and `\\s` are
    already Python-compatible, so this is a narrow shim rather than a general
    translator. If the parser starts using a JS-only construct, this raises and
    the test fails loudly instead of quietly testing a different regex.
    """
    if "(?<" in pattern and "(?<=" not in pattern:
        raise ValueError(f"named JS group in {pattern!r} — translate it explicitly")
    return pattern


@cache
def subject_pattern() -> re.Pattern[str]:
    match = _SUBJECT_RE.search(parser_code())
    if match is None:
        raise ValueError("the parser no longer extracts the subject with text.match(/.../)")
    return re.compile(_js_to_python(match.group("pattern")))


@cache
def strip_pattern() -> re.Pattern[str]:
    match = _STRIP_RE.search(parser_code())
    if match is None:
        raise ValueError("the parser no longer strips the SUBJECT line with text.replace(/.../)")
    return re.compile(_js_to_python(match.group("pattern")))


def parse(model_output: str) -> tuple[str | None, str]:
    """Run the parser's extraction over a model response.

    Returns `(subject, exec_summary)`, with `subject` **None** when the regex
    misses — where the shipped JavaScript substitutes a hardcoded default. The
    difference matters: the workflow's fallback is what makes the failure
    silent, and an eval that reproduced the fallback would reproduce the silence.
    """
    text = re.sub(r"^```html\n?", "", model_output, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text, flags=re.IGNORECASE).strip()
    found = subject_pattern().search(text)
    subject = found.group(1).strip() if found else None
    summary = strip_pattern().sub("", text, count=1).strip()
    return subject, summary
