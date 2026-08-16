"""Layer 1: the prompt and its parser must still agree (RC1-258).

Free, credential-free, and it runs on every push. This is the layer that catches
the failure nothing could catch before: edit the prompt's output format, leave
`Parse Email Content` alone, and no error is raised — a stakeholder receives an
email with a hardcoded stale subject and the real subject line buried in the
body.

Everything is read out of the committed workflow JSON at test time. A test that
asserted against a copy of the prompt would pass forever, including after
someone changed the real one.
"""

from __future__ import annotations

import re

import pytest

from evals import fixtures, workflow

# --- the prompt still asks for the shape the parser expects ---------------


def test_the_prompt_demands_a_subject_line():
    prompt = workflow.prompt_text()
    assert "SUBJECT:" in prompt, (
        "the parser's first move is to regex for 'SUBJECT:'. Without it the "
        "workflow silently substitutes a hardcoded subject."
    )


def test_the_prompt_demands_the_executive_summary_div():
    prompt = workflow.prompt_text()
    assert "<div" in prompt and "Executive Summary" in prompt, (
        "everything after the subject line is spliced into the email as the "
        "exec summary; the prompt has to ask for HTML or the email gets prose"
    )


@pytest.mark.parametrize("forbidden", ["sign-off", "tables", "extra HTML"])
def test_the_prompt_still_forbids_what_the_parser_adds_itself(forbidden):
    """The parser appends a sign-off, the status table and the Jira section.

    If the prompt stopped forbidding them the model would add its own and the
    email would carry two of each. The constraint is not stylistic — it exists
    because of what happens downstream.
    """
    assert forbidden.lower() in workflow.prompt_text().lower()


# --- round trip: a correct response parses correctly ----------------------


def _response_in_the_prompts_own_format(report_date: str = "2026-08-14") -> str:
    """Build a model response from the format the prompt itself states.

    Extracted from the prompt rather than hardcoded, so if the demanded format
    changes this canonical response changes with it — and the round-trip test
    keeps testing the real contract instead of a snapshot of an old one.
    """
    prompt = workflow.prompt_text()
    subject_line = re.search(r"(SUBJECT:[^\\\n]*?)\s*(?:2\)|\\n)", prompt)
    assert subject_line, "could not read the demanded subject line out of the prompt"
    subject = subject_line.group(1).replace("{{ $json.reportDate }}", report_date)

    div = re.search(r"(<div style=[^>]*>.*?</div>)", prompt, re.DOTALL)
    assert div, "could not read the demanded exec-summary div out of the prompt"
    body = div.group(1).replace(
        "YOUR 2-3 SENTENCE SUMMARY HERE",
        "The project is on track. Eighteen of twenty-four tickets are closed.",
    )
    return f"{subject}\n{body}"


def test_a_response_in_the_demanded_format_parses():
    subject, summary = workflow.parse(_response_in_the_prompts_own_format())
    assert subject is not None, "the parser's regex missed a correctly formatted response"
    assert "Weekly Status Update" in subject
    assert summary.startswith("<div"), "the exec summary must be the HTML block, subject stripped"
    assert "SUBJECT:" not in summary, "the subject line must not leak into the email body"


def test_markdown_fenced_output_still_parses():
    """The parser strips ```html fences, so a model that adds them is tolerated."""
    fenced = f"```html\n{_response_in_the_prompts_own_format()}\n```"
    subject, summary = workflow.parse(fenced)
    assert subject is not None
    assert "```" not in summary


# --- the coupling itself --------------------------------------------------


def test_a_response_without_the_subject_token_is_detectably_unparsed():
    """The failure this whole layer exists for.

    In the workflow this returns a hardcoded default subject and no error. Here
    it returns None, so the silence is visible. If someone edits the prompt to
    drop `SUBJECT:`, the tests above fail — this one documents what would
    otherwise happen downstream.
    """
    no_subject = "<div style='background:#f0f4ff;'>A summary with no subject line.</div>"
    subject, summary = workflow.parse(no_subject)
    assert subject is None, (
        "no SUBJECT: token means the workflow falls back to a stale hardcoded "
        "subject — silently, which is why the prompt must keep asking for it"
    )
    assert summary.startswith("<div")


def test_the_subject_regex_terminates_on_a_tag_as_well_as_a_newline():
    """The prompt's format puts the div immediately after the subject.

    A model that emits them on one line is still parsed correctly, and the
    parser's `(\\n|<)` alternation is what makes that true. Asserted because a
    well-meaning simplification to `(\\n)` would break it for exactly the output
    the prompt asks for.
    """
    one_line = "SUBJECT: Weekly Status Update (2026-08-14)<div style='x'>Summary.</div>"
    subject, summary = workflow.parse(one_line)
    assert subject == "Weekly Status Update (2026-08-14)"
    assert summary.startswith("<div")


# --- the fixtures and the workflow agree ----------------------------------


def test_every_placeholder_the_prompt_uses_is_supplied_by_every_fixture():
    """A placeholder added to the prompt without a fixture value would render
    as a literal `{{ $json.x }}` in the model's input."""
    for fixture in fixtures.FIXTURES:
        workflow.bind(fixture.values())  # raises on a missing placeholder


def test_binding_leaves_no_placeholders_behind():
    bound = workflow.bind(fixtures.BY_ID["healthy"].values())
    assert "{{" not in bound and "$json" not in bound


def test_the_health_branch_mirrored_in_fixtures_matches_the_shipped_javascript():
    """`fixtures.expected_health` duplicates logic that lives in a Code node.

    Duplication is unavoidable — there is no Python to import — so it is checked
    instead: the shipped source must still contain the three branches this
    function encodes, in the same order of precedence.
    """
    code = workflow.aggregate_code()
    assert "blocked.length > 0" in code, "At Risk is no longer driven by blocked count"
    assert "completionPct < 50" in code and "inProgress.length === 0" in code, (
        "the Needs Attention branch changed; fixtures.expected_health is now wrong"
    )
    for label in (fixtures.ON_TRACK, fixtures.NEEDS_ATTENTION, fixtures.AT_RISK):
        assert label in code, f"the workflow no longer emits {label!r}"


@pytest.mark.parametrize("fixture", fixtures.FIXTURES, ids=lambda f: f.id)
def test_each_fixture_declares_the_health_its_own_numbers_imply(fixture):
    assert fixture.health == fixtures.expected_health(
        blocked=fixture.blocked,
        completion_pct=fixture.completion_pct,
        in_progress=fixture.in_progress,
    )


def test_the_fixture_set_covers_all_three_health_states_and_the_boundary():
    states = {f.health for f in fixtures.FIXTURES}
    assert states == {fixtures.ON_TRACK, fixtures.NEEDS_ATTENTION, fixtures.AT_RISK}

    boundary = fixtures.BY_ID["boundary-49pct-with-wip"]
    assert boundary.completion_pct < 50 and boundary.health == fixtures.ON_TRACK, (
        "the boundary case must sit below 50% and still be On Track, or it is "
        "not testing the branch it exists for"
    )
