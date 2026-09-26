"""A market may be measured badly enough not to stake and still be measured.

The distinction this file defends: `STAKE_EXCLUDED_MARKETS` withholds the
STAKE and nothing else. The market stays allowlisted, stays eligible, stays
priced, keeps its opinion on the card as a lean, and keeps every row it
contributes to the forward ledger.

That last one is the whole point. `write_snapshot` runs on the unfiltered
price frame before `build_card` is called at all, and `docs/when_this_ends.md`
says the forward test scores opinions rather than bets -- "the card is dark and
places none, but a frozen opinion scored against the price it was frozen at is
the same test". So declining to stake a market costs no forward evidence, which
is what makes this a cheap decision rather than a trade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    HARD_GATED_MARKETS,
    LEANS_SECTION,
    PASSES_SECTION,
    STAKE_EXCLUDED_MARKETS,
    build_candidates,
)

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _row(
    *,
    market: str = "points",
    player: str = "Auston Matthews",
    selection: str = "over",
    line: float | None = 0.5,
    price: float = 150,
) -> dict:
    return {
        "date": "2026-10-08",
        "commence_time": _at(4),
        "home_team": "TOR",
        "away_team": "BOS",
        "market": market,
        "player": player,
        "selection": selection,
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


def _split(rows: list[dict], probability: float = 0.90):
    probabilities = {_key(row): probability for row in rows}
    selections, passes = build_candidates(pd.DataFrame(rows), probabilities)
    return selections, passes


def _staked(rows, probability: float = 0.90):
    selections, _ = _split(rows, probability)
    return [s for s in selections if s.section == BEST_BETS_SECTION]


def _leans(rows, probability: float = 0.90):
    selections, _ = _split(rows, probability)
    return [s for s in selections if s.section == LEANS_SECTION]


class TestTheExclusionIsAStakeDecisionOnly:
    def test_points_clears_the_bar_and_is_still_not_staked(self):
        rows = [_row()]
        assert _staked(rows) == [], (
            "points is in STAKE_EXCLUDED_MARKETS, so no rung of it may carry "
            "a stake however large the edge"
        )

    def test_it_becomes_a_lean_and_never_a_pass(self):
        rows = [_row()]
        selections, passes = _split(rows)
        leans = [s for s in selections if s.section == LEANS_SECTION]
        assert len(leans) == 1, "the opinion must survive as a lean"
        assert leans[0].section != PASSES_SECTION
        assert not any(p.market == "points" for p in passes), (
            "a withheld stake is not a pass -- a pass means the model "
            "declined, and here the model did not"
        )

    def test_the_withheld_stake_is_zero_units(self):
        assert _leans([_row()])[0].suggested_units == 0.0

    def test_the_lean_says_why_the_stake_was_withheld(self):
        reason = _leans([_row()])[0].demotion_reason
        assert reason, "a withheld stake must name its reason"
        assert "-4.2%" in reason
        assert "6,140" in reason

    def test_the_edge_and_the_model_probability_are_untouched(self):
        """The card must not pretend the model said something else."""
        lean = _leans([_row()], probability=0.90)[0]
        assert lean.model_probability == pytest.approx(0.90)
        assert lean.edge == pytest.approx(0.90 - lean.implied_probability)

    def test_every_rung_of_an_excluded_ladder_is_kept_as_a_lean(self):
        """Nothing is deleted: the ladder collapse and this exclusion both
        demote, and a rung may not be lost to the pair of them."""
        rows = [_row(line=0.5), _row(line=1.5), _row(line=2.5)]
        selections, passes = _split(rows)
        assert len(selections) + len(passes) == 3
        assert len(_leans(rows)) == 3
        assert _staked(rows) == []


class TestEveryOtherMarketIsUnaffected:
    @pytest.mark.parametrize(
        "market,line",
        [("blocked_shots", 1.5), ("shots_on_goal", 2.5), ("assists", 0.5)],
    )
    def test_a_market_not_on_the_list_still_stakes(self, market, line):
        staked = _staked([_row(market=market, line=line)])
        assert len(staked) == 1, f"{market} is not excluded and must stake"
        assert staked[0].suggested_units > 0.0

    def test_removing_the_entry_restores_the_stake(self, monkeypatch):
        """Reversible by deleting one dict entry -- and this proves the
        exclusion is the only thing stopping the stake, not some other gate
        that happens to catch points too."""
        monkeypatch.delitem(STAKE_EXCLUDED_MARKETS, "points")
        staked = _staked([_row()])
        assert len(staked) == 1
        assert staked[0].suggested_units > 0.0

    def test_an_excluded_market_does_not_suppress_a_staked_one_beside_it(self):
        rows = [_row(market="points"), _row(market="blocked_shots", line=1.5)]
        staked = _staked(rows)
        assert [s.market for s in staked] == ["blocked_shots"]


class TestItIsNotTheOtherKindOfGate:
    def test_points_is_not_hard_gated(self):
        """HARD_GATED_MARKETS is about information this lab does not have, and
        says outright it is 'not a judgement that the market has no value'.
        This exclusion is exactly that judgement, so it must not be smuggled
        into the other dict, where it would read as a data problem."""
        assert "points" not in HARD_GATED_MARKETS

    def test_the_two_lists_do_not_overlap(self):
        assert not (set(HARD_GATED_MARKETS) & set(STAKE_EXCLUDED_MARKETS))

    def test_the_reason_cites_a_measurement_and_a_sample_size(self):
        """House rule: a number without its sample size is not a finding."""
        for market, reason in STAKE_EXCLUDED_MARKETS.items():
            assert "%" in reason, f"{market} gives no measured return"
            assert "wager" in reason or "bet" in reason, (
                f"{market} states a return with no sample size beside it"
            )


class TestTheForwardLedgerIsUnaffected:
    """The claim this whole decision rests on, given a test.

    Withholding a stake is only cheap if the market keeps being measured. If
    the forward ledger recorded stakes instead of opinions, excluding `points`
    would quietly drop it from the one test `docs/when_this_ends.md` says is
    left, and the decision would be a real trade rather than a free one.
    """

    def test_an_excluded_market_still_freezes_into_the_snapshot(self, tmp_path):
        from nhl_betting_lab.forward_evidence import write_snapshot

        rows = [_row(line=0.5), _row(line=1.5), _row(line=2.5)]
        probabilities = {_key(row): 0.90 for row in rows}

        # Nothing on this market is staked...
        assert _staked(rows) == []

        # ...and every rung is frozen anyway.
        written = write_snapshot(
            pd.DataFrame(rows),
            probabilities,
            key_for=selection_key,
            verdicts_line="no verdict ships",
            snapshot_date="2026-10-08",
            now=NOW,
            archive_dir=tmp_path,
        )
        assert written is not None
        frozen = pd.read_csv(written)
        assert sorted(frozen["line"].tolist()) == [0.5, 1.5, 2.5]
        assert set(frozen["market"]) == {"points"}

    def test_the_snapshot_schema_carries_no_stake_at_all(self, tmp_path):
        """Not an accident to be preserved by luck: the frozen row has no
        column for a stake, a section or a unit count, so no future change to
        the staking path can reach the ledger without adding one."""
        from nhl_betting_lab.forward_evidence import write_snapshot

        rows = [_row(line=0.5)]
        written = write_snapshot(
            pd.DataFrame(rows),
            {_key(rows[0]): 0.90},
            key_for=selection_key,
            verdicts_line="no verdict ships",
            snapshot_date="2026-10-08",
            now=NOW,
            archive_dir=tmp_path,
        )
        columns = set(pd.read_csv(written).columns)
        for forbidden in ("section", "suggested_units", "units", "stake", "tier"):
            assert forbidden not in columns, (
                f"the snapshot now carries `{forbidden}`, so the forward test "
                "is no longer independent of what the card staked -- and "
                "STAKE_EXCLUDED_MARKETS stopped being free"
            )
