"""Every figure in the `points` stake-exclusion reason names the window it came from.

The backtest prices each wager at one distance from face-off, and the two
windows it measures are two different questions: the `card` window (about 9.6
hours out, `data/outputs/player_props_backtest_card.md`) and the `late` window
(about 4.1 hours out, `data/outputs/player_props_backtest.md`). The reports say
so themselves: "A return measured at one distance from the puck is not
comparable to one measured at another."

The reason text once read as one measurement while quoting both. Its headline
(-4.2% over 6,140, -256.8 units, eight markets corrected for) is the card
window; its "holds within 2025-26 alone (-5.4% over 3,468)" is the late
window's 2025-26 slice in `replication.md` (2,726 + 3,468 = 6,194 late-window
bets); and the evidence bundle verdict it quotes sits beside the late-window
-4.4% over 6,194. Nothing in the sentence said the second half was a different
window.

These tests read the figures out of the committed reports rather than pinning
the reason word for word: a sentence carrying a figure must name exactly one
window, and every figure in it must appear in THAT window's evidence. Rewording
is free; mixing windows unlabelled is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nhl_betting_lab.reports.gameday_card import STAKE_EXCLUDED_MARKETS

OUTPUTS = Path(__file__).resolve().parents[1] / "data" / "outputs"

WINDOW_NAMES = {"card": "card window", "late": "late window"}

#: A signed or unsigned number, with thousands separators and decimals.
NUMBER = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?")

#: Tokens that are figures in English rather than digits.
NUMBER_WORDS = {"seven": "7", "eight": "8"}

#: Numbers that are not measurements: the interval level and the season label.
NOT_A_FIGURE = re.compile(r"95% interval|\b\d{4}-\d{2}\b")


def _norm(token: str) -> str:
    return token.replace(",", "").lstrip("+")


def _figures(text: str) -> set[str]:
    text = NOT_A_FIGURE.sub(" ", text)
    found = {_norm(t) for t in NUMBER.findall(text)}
    for word, digit in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            found.add(digit)
    return found


def _points_row(report: str) -> str:
    for line in (OUTPUTS / report).read_text().splitlines():
        if line.startswith("| `points`"):
            return line
    raise AssertionError(f"no points row in {report}")


#: A count as the reports print it: bare today, perhaps with thousands
#: separators after a regeneration.
COUNT = r"(\d{1,3}(?:,\d{3})+|\d+)"


def _find(pattern: str, text: str, source: str) -> str:
    """The first group of `pattern` in `text`, or a failure naming both."""
    found = re.search(pattern, text)
    assert found, f"{source}: no match for {pattern!r}; has the report's wording changed?"
    return found.group(1)


def _count(token: str) -> int:
    return int(token.replace(",", ""))


def _evidence(report: str) -> str:
    """The points row, the pricing distance and the correction count."""
    text = (OUTPUTS / report).read_text()
    hours = _find(r"Priced \*\*([\d.]+) hours", text, report)
    # The committed reports say "correcting for the 8 markets tested"; the
    # generator now writes "correcting for the 8 figures measured on the same
    # data (7 markets and the overall figure)" (`stats.correction_family`).
    # Either reading is the same count, and both must be accepted, or the
    # next regeneration breaks this test for a reason unrelated to its claim.
    tested = _find(
        rf"points`: .*?correcting for the {COUNT} (?:markets|figures)", text, report
    )
    return f"{_points_row(report)} {hours} {tested} {_market_rows(report)}"


def _market_rows(report: str) -> int:
    """How many markets the report's result table measures.

    The correction's family is these plus the overall "All props" row, which
    is why the committed card report's "8 markets tested" is 7 markets.
    """
    rows = [
        line
        for line in (OUTPUTS / report).read_text().split("### ")[0].splitlines()
        if line.startswith("| `")
    ]
    assert rows, f"{report}: no market rows found in the result table"
    return len(rows)


@pytest.fixture(scope="module")
def evidence() -> dict[str, set[str]]:
    card = _figures(_evidence("player_props_backtest_card.md"))
    # The per-season split in replication.md is the late window cut in two:
    # its points rows sum to the late report's bet count, not the card's.
    late = _figures(_evidence("player_props_backtest.md") + " " + _points_row("replication.md"))
    return {"card": card, "late": late}


@pytest.fixture(scope="module")
def sentences() -> list[str]:
    reason = STAKE_EXCLUDED_MARKETS["points"]
    return [s for s in re.split(r"(?<=[.;])\s+", reason) if s.strip()]


def test_the_replication_split_is_the_late_window():
    """The premise: 2024-25 + 2025-26 in replication.md is the late count."""
    split = re.findall(rf"/ {COUNT} bets", _points_row("replication.md"))
    assert len(split) == 2, f"replication.md: expected two season counts, got {split}"
    late_bets = _find(
        rf"\| {COUNT} \|", _points_row("player_props_backtest.md"), "player_props_backtest.md"
    )
    card_bets = _find(
        rf"\| {COUNT} \|",
        _points_row("player_props_backtest_card.md"),
        "player_props_backtest_card.md",
    )
    seasons = sum(map(_count, split))
    assert seasons == _count(late_bets)
    assert seasons != _count(card_bets)


def test_every_sentence_with_a_figure_names_exactly_one_window(sentences):
    for sentence in sentences:
        if not _figures(sentence):
            continue
        named = [w for w, label in WINDOW_NAMES.items() if label in sentence.lower()]
        assert len(named) == 1, (
            f"a figure must be attributed to one window; this sentence names "
            f"{named or 'none'}: {sentence!r}"
        )


def test_every_figure_belongs_to_the_window_its_sentence_names(sentences, evidence):
    for sentence in sentences:
        figures = _figures(sentence)
        for window, label in WINDOW_NAMES.items():
            if label in sentence.lower():
                stray = figures - evidence[window]
                assert not stray, (
                    f"{sorted(stray)} labelled {label} but not in that "
                    f"window's report: {sentence!r}"
                )


def test_the_headline_and_the_late_figures_are_both_present_and_labelled(sentences):
    """Guards against 'fixing' the mix by deleting half the evidence."""

    def sentence_with(figure: str) -> str:
        hits = [s for s in sentences if figure in s]
        assert hits, f"{figure} is missing from the reason"
        return hits[0].lower()

    for figure in ("-4.2%", "6,140", "-256.8"):
        assert "card window" in sentence_with(figure)
    for figure in ("-5.4%", "3,468"):
        assert "late window" in sentence_with(figure)


def test_the_quoted_bundle_verdict_is_attributed_to_the_late_window(sentences):
    bundle = (OUTPUTS / "allowlist_evidence_bundle.md").read_text()
    verdict = "a loss that survives the correction still argues against enabling this market"
    assert verdict in bundle.replace("A loss", "a loss")
    quoting = [s for s in sentences if verdict in s.lower()]
    assert quoting, "the reason should still quote the evidence bundle"
    for sentence in quoting:
        assert "late window" in sentence.lower(), sentence
        assert "card window" not in sentence.lower(), sentence


def test_the_card_correction_counts_figures_not_markets(sentences):
    """The card window's family is its markets plus the overall figure.

    `stats.correction_family` records the error this guards: "8 markets
    tested" for a window that measures 7. The committed report still says
    it that way, so the count is read from the report (either wording) and
    the market count from its table, and the reason must say figures.
    """
    report = "player_props_backtest_card.md"
    text = (OUTPUTS / report).read_text()
    looks = _count(
        _find(rf"points`: .*?correcting for the {COUNT} (?:markets|figures)", text, report)
    )
    markets = _market_rows(report)
    assert looks == markets + 1, (
        f"{report}: expected the family to be {markets} markets plus the "
        f"overall figure, found {looks} looks"
    )

    card = [s for s in sentences if "card window" in s.lower()]
    assert card, "no sentence names the card window"
    card_text = " ".join(card)
    assert re.search(rf"\b{looks} figures measured\b", card_text), card_text
    assert f"({markets} markets and the overall figure)" in card_text, card_text
    assert not re.search(r"\b(?:eight|8) markets\b", card_text, re.IGNORECASE), (
        "the card window's correction counts the overall figure too; "
        f"calling all {looks} looks markets is the error correction_family names"
    )
