"""Layer 2: the prompt, run for real and scored (RC1-258).

Binds a fixture into the *committed* prompt, calls the Messages API directly
with the model the workflow pins, and scores the response. No n8n runtime, no
Notion, no Jira, no Gmail — and nothing is emailed.

## The strongest check is the cheapest one

`parses-through-the-shipped-parser` runs the real model's real output through
the regexes read out of `Parse Email Content`. Layer 1 proves the prompt and the
parser agree *in principle*, against a response built to the stated format.
This proves the model actually produces that format. The two are different
questions and the second one cannot be answered without spending money.

## The model restates health, it does not decide it

`Aggregate & Summarize Data` computes health deterministically — At Risk if
anything is blocked, Needs Attention below 50% with nothing in progress, On
Track otherwise. The prompt hands the answer over. So an output asserting a
different state is a factual error, not a stylistic one, and it is scored the
same way the drift digest scores a re-ranked severity: the model was told the
answer and got it wrong.

That check needs the *other* two states to be absent, not just the right one
present — "the project is on track, though some items are at risk" contains
both, and a substring test for the correct label alone would pass it.

## Why `agent_evals.groundedness`'s health check does not transfer

It has one, with the subject-proximity and negation handling that five rounds of
false positives bought. It cannot be used here: its phrase lists encode the
planner's vocabulary, where **"at risk" is the yellow state**. In this workflow
"At Risk" is *red* and "Needs Attention" is yellow. Mapping one onto the other
would invert two of the three states.

So the vocabulary is repo-local and the *structure* is borrowed. Both guards
below were bought the same way — by running it:

* **a goal is not a claim.** "two items blocked that require immediate attention
  to keep the release **on track**" is a correct At Risk summary. A bare
  substring test read it as asserting On Track.
* **the state has synonyms.** The model wrote "**requires** attention" where the
  workflow's label says "Needs Attention". Demanding the label verbatim failed a
  summary that was exactly right.
"""

from __future__ import annotations

import re
import time

from agent_evals import pricing
from agent_evals.case import Case
from agent_evals.record import CaseResult, CharacteristicResult, SubjectVersion, Usage

from evals import fixtures, workflow

NAME = "stakeholder-status-email"

#: What the parser appends itself. A model that adds its own produces an email
#: carrying two of each — which is why the prompt forbids them and why this is
#: scored rather than assumed.
_FORBIDDEN = (
    "best regards",
    "sincerely",
    "kind regards",
    "<table",
    "<h1",
    "<h2 style=\"color:#2c3e50;margin-top:32px",
)

CASES: tuple[Case, ...] = tuple(
    Case(
        id=f.id,
        input={"fixture": f.id},
        expect=(
            "parses-through-the-shipped-parser",
            "states-the-counts",
            "restates-the-computed-health",
            "adds-nothing-the-parser-appends",
        ),
        tags=("status-email", f.health),
    )
    for f in fixtures.FIXTURES
)


def preflight(api_key: str | None) -> None:
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Layer 1 (`pytest`) needs no key and covers "
            "the prompt/parser contract; this layer calls the model."
        )


def prompt_version() -> str:
    import hashlib

    return f"prompt-sha256:{hashlib.sha256(workflow.prompt_text().encode()).hexdigest()[:12]}"


def version() -> SubjectVersion:
    return SubjectVersion(
        subject=NAME,
        code_version=_workflow_version(),
        model=workflow.model(),
        prompt_version=prompt_version(),
    )


def _workflow_version() -> str:
    """A hash of the whole workflow file.

    n8n has no version marker to read, so the file itself is the version. It is
    noisier than a hand-bumped number — an unrelated node edit moves it — but a
    version that moves too often is recoverable, and one that silently does not
    move is not.
    """
    import hashlib

    return f"workflow-sha256:{hashlib.sha256(workflow.WORKFLOW_PATH.read_bytes()).hexdigest()[:12]}"


def _parses(text: str) -> CharacteristicResult:
    subject, summary = workflow.parse(text)
    ok = subject is not None and summary.lstrip().startswith("<div")
    return CharacteristicResult(
        name="parses-through-the-shipped-parser",
        passed=ok,
        detail=(
            f"subject {subject!r}, summary is the exec-summary div"
            if ok
            else (
                "no SUBJECT: match — the workflow would silently send a stale hardcoded subject"
                if subject is None
                else f"summary does not start with the div: {summary[:60]!r}"
            )
        ),
    )


def _states_counts(text: str, fixture: fixtures.Fixture) -> CharacteristicResult:
    """The numbers the prompt hands over must appear.

    Digits only, and that is a deliberate limitation: a summary writing "three
    quarters complete" is correct and would fail here. The prompt asks for a
    C-suite summary of specific figures, so the risk being scored is a *wrong*
    number rather than a spelled-out one — and the observation records the text
    so a spelled-out failure is readable rather than mysterious.
    """
    required = {
        "completion %": str(fixture.completion_pct),
        "done count": str(fixture.done),
        "total": str(fixture.total),
    }
    missing = [label for label, value in required.items() if value not in text]
    return CharacteristicResult(
        name="states-the-counts",
        passed=not missing,
        detail=(
            "states completion, done and total"
            if not missing
            else f"missing as digits: {', '.join(missing)}"
        ),
    )


#: This workflow's vocabulary, with the synonyms a model actually reaches for.
#: Written with spaces; `_flatten` makes separators irrelevant, so "at-risk" and
#: "needs-attention state" match without needing their own entries.
_HEALTH_PHRASES: dict[str, tuple[str, ...]] = {
    fixtures.ON_TRACK: ("on track", "on schedule", "tracking well", "healthy"),
    fixtures.NEEDS_ATTENTION: (
        "needs attention",
        "requires attention",
        "require attention",
        "needing attention",
        "need attention",
        "requiring attention",
        "needs focus",
        "warrants attention",
    ),
    fixtures.AT_RISK: ("at risk", "off track", "in jeopardy"),
}


def _flatten(text: str) -> str:
    """Collapse hyphens and whitespace so separators cannot hide a phrase.

    The third phrasing false positive this check produced, and the one that
    changed the fix from "add another synonym" to "stop treating separators as
    meaning". The model wrote "is currently in a **needs-attention** state" — a
    correct restatement that a space-separated list missed. Enumerating
    spellings loses that race; normalising ends it.
    """
    return re.sub(r"[\s\-–—]+", " ", text.lower())

#: Words that turn a state phrase into an aspiration. "keep the release on
#: track" is a goal; "the release is on track" is a claim. Only the second is an
#: assertion about health.
_GOAL_CONTEXT = re.compile(
    r"\b(?:keep|keeps|keeping|get|gets|getting|back|return|returning|stay|staying|"
    r"remain\s+on\s+schedule|bring|bringing|restore|restoring)\b[^.]{0,40}$"
)


def _asserted(lowered: str, phrase: str) -> bool:
    """Is `phrase` claimed as the current state, rather than aimed at?"""
    for match in re.finditer(re.escape(phrase), lowered):
        preceding = lowered[max(0, match.start() - 60) : match.start()]
        if _GOAL_CONTEXT.search(preceding):
            continue
        return True
    return False


def _restates_health(text: str, fixture: fixtures.Fixture) -> CharacteristicResult:
    """The computed state, and not either of the other two."""
    lowered = _flatten(text)
    present = [
        state
        for state, tokens in _HEALTH_PHRASES.items()
        if any(_asserted(lowered, _flatten(t)) for t in tokens)
    ]
    correct = fixture.health in present
    contradicting = [s for s in present if s != fixture.health]
    return CharacteristicResult(
        name="restates-the-computed-health",
        passed=correct and not contradicting,
        detail=(
            f"restates {fixture.health}"
            if correct and not contradicting
            else (
                f"asserts {', '.join(contradicting)} — the rules computed {fixture.health}"
                if contradicting
                else f"never states {fixture.health}"
            )
        ),
    )


def _adds_nothing_extra(text: str) -> CharacteristicResult:
    lowered = text.lower()
    added = [token for token in _FORBIDDEN if token in lowered]
    return CharacteristicResult(
        name="adds-nothing-the-parser-appends",
        passed=not added,
        detail=(
            "no sign-off, table or heading of its own"
            if not added
            else f"would be duplicated downstream: {', '.join(added)}"
        ),
    )


def _length(text: str) -> CharacteristicResult:
    """Advisory. The prompt asks for 2-3 sentences in the summary paragraph.

    Advisory because sentence counting is unreliable prose analysis — an
    abbreviation or a decimal splits a sentence — and a flaky gate gets disabled.
    Reported so a prompt edit that makes the summary balloon is visible.
    """
    inner = re.sub(r"<[^>]+>", " ", text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", inner.strip()) if len(s.split()) > 2]
    return CharacteristicResult(
        name="summary-is-two-to-three-sentences",
        passed=2 <= len(sentences) <= 4,
        detail=f"{len(sentences)} sentence(s) after stripping tags",
        advisory=True,
    )


def run(case: Case, client) -> CaseResult:
    fixture = fixtures.BY_ID[case.input["fixture"]]
    bound = workflow.bind(fixture.values())
    started = time.perf_counter()
    try:
        response = client.messages.create(
            model=workflow.model(),
            max_tokens=1000,
            messages=[{"role": "user", "content": bound}],
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            usage=Usage(latency_ms=(time.perf_counter() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = (time.perf_counter() - started) * 1000

    subject, summary = workflow.parse(text)
    input_tokens = getattr(response.usage, "input_tokens", 0)
    output_tokens = getattr(response.usage, "output_tokens", 0)
    return CaseResult(
        case_id=case.id,
        characteristics=[
            _parses(text),
            _states_counts(text, fixture),
            _restates_health(text, fixture),
            _adds_nothing_extra(text),
            _length(summary or text),
        ],
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            # Priced, not counted: recording $0 for a billed run is RC1-254's
            # exact finding, and the trend page dutifully displayed it (RC1-269).
            cost_usd=pricing.cost_usd(workflow.model(), input_tokens, output_tokens),
            latency_ms=latency_ms,
        ),
        observations={
            "health_expected": fixture.health,
            "subject": subject,
            # The output itself. A golden whose failures cannot be read
            # afterwards is half a golden.
            "output": text,
        },
    )
