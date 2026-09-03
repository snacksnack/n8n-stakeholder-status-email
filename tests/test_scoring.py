"""The layer-2 scorers, checked in both directions (RC1-258).

Free — no credentials, no tokens. Layer 2 itself is billed and stays out of CI,
but its *scoring* is ordinary code and the place mistakes actually live. Both
health guards below were bought by a real run flagging a correct summary, so
each has a test proving it still fails on a genuinely wrong one.
"""

from __future__ import annotations

import pytest

from evals import fixtures, subject, workflow

BLOCKED = fixtures.BY_ID["blocked"]
ZERO = fixtures.BY_ID["zero-completion"]
HEALTHY = fixtures.BY_ID["healthy"]


def test_the_correct_state_passes_and_a_contradicting_one_fails():
    assert subject._restates_health("The project is at risk this week.", BLOCKED).passed

    wrong = subject._restates_health("The project is on track this week.", BLOCKED)
    assert not wrong.passed, "asserting On Track for a blocked week overrides the rules engine"
    assert "At Risk" in wrong.detail


def test_a_goal_is_not_a_claim_about_health():
    """The false positive from the first real run.

    "two items blocked that require immediate attention to keep the release on
    track" is a correct At Risk summary. A bare substring test read the trailing
    "on track" as asserting the opposite state.
    """
    real_output = (
        "The AI Incident Summarizer (RC1) is currently at risk, with 2 items blocked "
        "that require immediate attention to keep the release on track."
    )
    assert subject._restates_health(real_output, BLOCKED).passed


def test_aiming_at_a_state_still_fails_when_the_right_one_is_never_claimed():
    """The guard must not become a blanket excuse for the word.

    If the summary only ever *aspires* to On Track and never states the computed
    state, that is a miss — the goal context suppresses a false contradiction,
    it does not supply a missing claim.
    """
    aspiring_only = "We are working to get the project back on track."
    result = subject._restates_health(aspiring_only, BLOCKED)
    assert not result.passed
    assert "never states" in result.detail


def test_a_verb_form_of_the_state_counts():
    """RC1-376: the model wrote "flagged as needing attention" for Needs Attention
    and the gate read it as never stated. The level was restated; the grammar moved."""
    assert subject._restates_health("The project health is flagged as needing attention.", ZERO).passed
    assert subject._restates_health("These items need attention this week.", ZERO).passed


def test_a_synonym_for_the_state_counts():
    """The model wrote "requires attention" where the label says "Needs Attention"."""
    assert subject._restates_health("The project requires attention.", ZERO).passed
    assert not subject._restates_health("The project is on track.", ZERO).passed


def test_a_hyphenated_state_is_still_the_state():
    """The third phrasing false positive, and the one that changed the fix.

    The model wrote "is currently in a needs-attention state" — correct, and
    missed by a space-separated phrase list. Separators are now normalised
    rather than enumerated.
    """
    assert subject._restates_health(
        "The project is currently in a needs-attention state.", ZERO
    ).passed
    assert subject._restates_health("The release is at-risk this week.", BLOCKED).passed

    # Normalising separators must not start matching across sentences.
    assert not subject._restates_health(
        "Work is on hold. Track progress in Jira.", HEALTHY
    ).passed, "'on' and 'track' in different sentences are not the phrase 'on track'"


def test_asserting_two_states_at_once_fails():
    both = "The project is on track, though the release is at risk."
    assert not subject._restates_health(both, HEALTHY).passed


def test_counts_must_appear_as_digits():
    ok = f"{HEALTHY.completion_pct}% complete, {HEALTHY.done} of {HEALTHY.total} closed."
    assert subject._states_counts(ok, HEALTHY).passed

    missing = f"{HEALTHY.completion_pct}% complete."
    result = subject._states_counts(missing, HEALTHY)
    assert not result.passed
    assert "done count" in result.detail


def test_a_sign_off_or_table_the_parser_already_appends_is_caught():
    assert subject._adds_nothing_extra("<div>A clean summary.</div>").passed

    for extra in ("<div>Summary.</div><p>Best regards, Reid</p>", "<div>x</div><table><tr></tr>"):
        assert not subject._adds_nothing_extra(extra).passed


def test_the_parse_check_fails_when_the_subject_line_is_missing():
    """The failure that ships a stale subject to stakeholders."""
    good = "SUBJECT: Weekly Status Update (2026-08-14)\n<div style='x'>Summary.</div>"
    assert subject._parses(good).passed

    result = subject._parses("<div style='x'>Summary with no subject line.</div>")
    assert not result.passed
    assert "stale hardcoded subject" in result.detail


@pytest.mark.parametrize("fixture", fixtures.FIXTURES, ids=lambda f: f.id)
def test_every_case_expects_the_four_gating_characteristics(fixture):
    case = next(c for c in subject.CASES if c.id == fixture.id)
    assert set(case.expect) == {
        "parses-through-the-shipped-parser",
        "states-the-counts",
        "restates-the-computed-health",
        "adds-nothing-the-parser-appends",
    }


def test_the_subject_version_records_the_prompt_and_the_workflow_separately():
    """A prompt edit and an unrelated node edit must be distinguishable."""
    version = subject.version()
    assert version.prompt_version.startswith("prompt-sha256:")
    assert version.code_version.startswith("workflow-sha256:")
    assert version.model == workflow.model()
