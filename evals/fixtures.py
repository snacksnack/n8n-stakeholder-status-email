"""Aggregate-node outputs, standing in for a week of real data (RC1-258).

Each fixture is what `Aggregate & Summarize Data` hands the Claude node. The
health values are not chosen by hand — they are computed by `expected_health`,
which mirrors the branch in that node's JavaScript, so a fixture cannot claim a
health state the workflow would not have produced.

The four cases cover the states and the boundary between them:

* **healthy** — work in flight, nothing blocked
* **blocked** — one blocked ticket, which is the only trigger for At Risk
* **zero-completion** — nothing done, nothing in progress, nothing blocked; the
  only path to Needs Attention
* **boundary** — 49% complete with work in progress. Below the 50% threshold and
  still On Track, because the Needs Attention branch also requires
  `inProgress === 0`. This is the case a reader of the prompt would most likely
  get wrong, which makes it the one worth freezing.
"""

from __future__ import annotations

from dataclasses import dataclass

ON_TRACK = "🟢 On Track"
NEEDS_ATTENTION = "🟡 Needs Attention"
AT_RISK = "🔴 At Risk"


def expected_health(*, blocked: int, completion_pct: int, in_progress: int) -> str:
    """The health branch from `Aggregate & Summarize Data`, in Python.

    Deliberately duplicated rather than imported — there is nothing to import
    from, the original is JavaScript inside a node. `test_contract.py` asserts
    this function still agrees with the shipped source, so the duplication is
    checked rather than trusted.
    """
    if blocked > 0:
        return AT_RISK
    if completion_pct < 50 and in_progress == 0:
        return NEEDS_ATTENTION
    return ON_TRACK


@dataclass(frozen=True)
class Fixture:
    id: str
    report_date: str
    done: int
    total: int
    in_progress: int
    blocked: int
    notes: str = ""

    @property
    def completion_pct(self) -> int:
        return round(self.done / self.total * 100) if self.total else 0

    @property
    def health(self) -> str:
        return expected_health(
            blocked=self.blocked,
            completion_pct=self.completion_pct,
            in_progress=self.in_progress,
        )

    def values(self) -> dict[str, object]:
        """Exactly the placeholder set the prompt interpolates."""
        return {
            "reportDate": self.report_date,
            "health": self.health,
            "completionPct": self.completion_pct,
            "doneCount": self.done,
            "total": self.total,
            "inProgressCount": self.in_progress,
            "blockedCount": self.blocked,
        }


FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        id="healthy",
        report_date="2026-08-14",
        done=18,
        total=24,
        in_progress=4,
        blocked=0,
        notes="75% complete, work in flight, nothing blocked.",
    ),
    Fixture(
        id="blocked",
        report_date="2026-08-14",
        done=11,
        total=24,
        in_progress=5,
        blocked=2,
        notes="Two blocked tickets. Blocked is the only trigger for At Risk.",
    ),
    Fixture(
        id="zero-completion",
        report_date="2026-08-14",
        done=0,
        total=14,
        in_progress=0,
        blocked=0,
        notes=(
            "Nothing done, nothing started, nothing blocked — the only route to "
            "Needs Attention, and the week a model is most tempted to narrate as "
            "progress."
        ),
    ),
    Fixture(
        id="boundary-49pct-with-wip",
        report_date="2026-08-14",
        done=49,
        total=100,
        in_progress=6,
        blocked=0,
        notes=(
            "Below the 50% threshold and still On Track, because the Needs "
            "Attention branch also requires inProgress === 0. The state a reader "
            "of the prompt is most likely to get wrong."
        ),
    ),
)

BY_ID: dict[str, Fixture] = {f.id: f for f in FIXTURES}
