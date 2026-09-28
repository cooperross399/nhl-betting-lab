"""A lean demoted from a stake is listed under the reason it was demoted.

Two passes turn a would-be stake into a lean at zero units, and each writes
its own sentence into `demotion_reason`:

* the one-stake-per-outcome pass, when a ladder priced one outcome at several
  lines and another rung kept the stake;
* `STAKE_EXCLUDED_MARKETS`, when the card does not stake the market at all on
  its measured return (`points`, today).

The rendered card used to gather every row carrying a reason under one
heading -- "One stake per outcome: where a ladder priced one outcome at
several lines, one rung is staked and the rest are recorded here." -- so a
lone `points` over 0.5 with no ladder anywhere near it was told it had lost
its stake to a sibling rung. That is the wrong reason, printed under the
right-looking one, and the only reader who could judge the demotion would
read the heading and not the sentence under it.

What this module holds the card to: each demoted row appears exactly once,
under a heading that states the reason it was demoted, and still at zero
units. Nothing becomes a pass and nothing disappears.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    EligibilityReport,
    MarketEligibility,
)
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    STAKE_EXCLUDED_MARKETS,
    build_card,
    render_card,
)

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)

#: The opening words of the ladder heading, as the card printed them before
#: this fix and still prints them for a collapsed ladder.
LADDER_HEADING = "One stake per outcome: where a ladder priced one outcome"


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _row(*, market: str, player: str, line: float, price: float = 150) -> dict:
    return {
        "date": "2026-10-08",
        "commence_time": _at(4),
        "home_team": "TOR",
        "away_team": "BOS",
        "market": market,
        "player": player,
        "selection": "over",
        "line": line,
        "american_odds": price,
        "book": "DraftKings",
    }


def _key(row: dict) -> tuple:
    """The real key function, never a hand copy."""
    return selection_key(
        SimpleNamespace(**row),
        market=row["market"],
        selection=row["selection"],
        line=row["line"],
    )


def _eligibility(markets: list[str]) -> EligibilityReport:
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[
            MarketEligibility(
                market=market, state=ELIGIBLE, reason="Allowlisted and complete."
            )
            for market in markets
        ],
    )


#: A lone `points` rung, far over the best-bet prop bar (edge +20% at +150),
#: with no other rung of its outcome anywhere on the slate. It is a lean only
#: because `points` is stake-excluded.
POINTS = (_row(market="points", player="Auston Matthews", line=0.5), 0.60)

#: A two-rung `shots_on_goal` ladder on another player, both rungs over the
#: best-bet bar. The 2.5 rung keeps the stake; the 3.5 rung is demoted by the
#: one-stake-per-outcome pass.
LADDER = [
    (_row(market="shots_on_goal", player="William Nylander", line=2.5), 0.60),
    (_row(market="shots_on_goal", player="William Nylander", line=3.5), 0.56),
]


def _card(entries):
    rows = [row for row, _ in entries]
    probabilities = {_key(row): p for row, p in entries}
    markets = sorted({row["market"] for row in rows})
    return build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(markets),
        now=NOW,
    )


def _paragraph_and_bullets(rendered: str) -> list[tuple[str, list[str]]]:
    """Every non-bullet paragraph followed by the bullet list under it.

    The card renders each group as a heading paragraph, a blank line, then
    one `- ` line per row. Reading it back this way ties a row to the heading
    it actually sits under, which is the thing the old card got wrong.
    """
    blocks = [block for block in rendered.split("\n\n") if block.strip()]
    grouped: list[tuple[str, list[str]]] = []
    for index, block in enumerate(blocks):
        lines = block.strip().splitlines()
        if lines[0].startswith("- ") or lines[0].startswith("|"):
            continue
        following = blocks[index + 1].strip().splitlines() if index + 1 < len(blocks) else []
        bullets = [line for line in following if line.startswith("- ")]
        if bullets and len(bullets) == len(following):
            grouped.append((block.strip(), bullets))
    return grouped


def _bullets_under(rendered: str, heading_starts: str) -> list[str]:
    found = [
        bullets
        for heading, bullets in _paragraph_and_bullets(rendered)
        if heading.startswith(heading_starts)
    ]
    assert len(found) <= 1, f"{heading_starts!r} headed more than one list"
    return found[0] if found else []


def _points_reason() -> str:
    return STAKE_EXCLUDED_MARKETS["points"]


# -- the defect ----------------------------------------------------------


def test_a_stake_excluded_row_is_not_listed_under_the_ladder_heading() -> None:
    card = _card([POINTS, *LADDER])
    rendered = render_card(card)

    under_ladder = _bullets_under(rendered, LADDER_HEADING)
    # Asserted first, so a card that dropped the ladder list cannot pass this
    # by having no list to be absent from.
    assert any("William Nylander over 3.5" in line for line in under_ladder)
    assert not any("Auston Matthews" in line for line in under_ladder), (
        "a stake-excluded points row sat under the one-stake-per-outcome "
        "heading, which tells the reader a sibling rung took its stake"
    )


def test_a_card_with_no_ladder_prints_no_ladder_heading() -> None:
    card = _card([POINTS])
    assert len(card.leans) == 1
    assert LADDER_HEADING not in render_card(card)


def test_the_stake_excluded_row_sits_under_its_own_measured_reason() -> None:
    rendered = render_card(_card([POINTS, *LADDER]))

    groups = [
        (heading, bullets)
        for heading, bullets in _paragraph_and_bullets(rendered)
        if any("Auston Matthews over 0.5" in line for line in bullets)
    ]
    assert len(groups) == 1, groups
    heading, bullets = groups[0]
    assert "`points`" in heading, "the heading must name the market"
    assert _points_reason() in heading, (
        "the heading must carry the reason the row itself carries"
    )
    assert not heading.startswith(card_module.LADDER_DEMOTION_PREFIX)
    assert not any("William Nylander" in line for line in bullets)


def test_a_ladder_only_card_prints_no_stake_withheld_group() -> None:
    rendered = render_card(_card(LADDER))
    assert _bullets_under(rendered, LADDER_HEADING)
    assert _points_reason() not in rendered


# -- nothing is lost to the split ----------------------------------------


def test_every_demoted_row_is_listed_exactly_once_at_zero_units() -> None:
    card = _card([POINTS, *LADDER])
    rendered = render_card(card)

    demoted = [row for row in card.leans if row.get("demotion_reason")]
    assert len(demoted) == 2, [row["demotion_reason"][:30] for row in demoted]
    assert all(row["suggested_units"] == 0.0 for row in demoted)
    assert not any(
        row.get("market") == "points" for row in card.passes
    ), "a withheld stake is never a pass"

    listed = [
        line
        for _heading, bullets in _paragraph_and_bullets(rendered)
        for line in bullets
        if "(`points`)" in line or "(`shots_on_goal`)" in line
    ]
    for label in ("Auston Matthews over 0.5", "William Nylander over 3.5"):
        assert sum(label in line for line in listed) == 1, (label, listed)
    # The rung that kept the stake is a best bet, not a demoted lean.
    assert not any("William Nylander over 2.5 (" in line for line in listed)


def test_a_whole_excluded_ladder_is_listed_once_per_rung() -> None:
    """Every rung of an excluded ladder is a lean for the exclusion's reason;
    none of them is a ladder demotion, because none of them was staked."""
    rungs = [
        (_row(market="points", player="Auston Matthews", line=line), p)
        for line, p in ((0.5, 0.60), (1.5, 0.56), (2.5, 0.54))
    ]
    card = _card(rungs)
    rendered = render_card(card)

    assert len(card.leans) == 3
    assert LADDER_HEADING not in rendered
    listed = [
        line
        for heading, bullets in _paragraph_and_bullets(rendered)
        if _points_reason() in heading
        for line in bullets
    ]
    for line_value in ("0.5", "1.5", "2.5"):
        label = f"Auston Matthews over {line_value}"
        assert sum(label in line for line in listed) == 1, (label, listed)


def test_a_reason_neither_pass_writes_is_still_listed_and_claims_nothing() -> None:
    """A future demotion must not vanish for want of a heading, and must not
    borrow either existing heading's explanation."""
    stray = dict(
        POINTS[0],
        market="assists",
        section=card_module.LEANS_SECTION,
        suggested_units=0.0,
        demotion_reason="A reason no pass writes today.",
    )
    card = _card([POINTS, *LADDER])
    lines = card_module._demoted_leans_by_reason([*card.leans, stray])
    rendered = "\n".join(lines)

    under_ladder = _bullets_under(rendered, LADDER_HEADING)
    assert not any("A reason no pass writes" in line for line in under_ladder)
    groups = [
        (heading, bullets)
        for heading, bullets in _paragraph_and_bullets(rendered)
        if any("A reason no pass writes" in line for line in bullets)
    ]
    assert len(groups) == 1, groups
    heading, bullets = groups[0]
    assert _points_reason() not in heading
    assert len(bullets) == 1 and "(`assists`)" in bullets[0]
