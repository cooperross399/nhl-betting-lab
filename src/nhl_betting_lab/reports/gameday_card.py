"""The gated gameday card.

The card is the only thing in this repository that recommends a bet, so it is
the thing with the most gates in front of it. In order:

1. **Policy.** Only markets a reviewed human approval allowlists can produce a
   selection. The repository ships allowlisting nothing, so by default this
   card produces nothing — and says so, rather than producing something.
2. **Eligibility.** A market must be priced for the whole slate. An
   `incomplete` market is excluded rather than half-used: picking only where
   prices happen to exist is a selection effect, not an edge.
3. **Model opinion.** No opinion, no selection. There is no fallback to a
   league-average price.
4. **Market-specific gates.** `goalie_saves` needs a confirmed starter, which
   this lab has no source for — see
   `docs/goalie_props_need_a_confirmed_starter.md`.
5. **Edge and juice.** A prop must clear a higher edge bar than a team market,
   and nothing worse than the configured juice limit is selected.
6. **The puck-drop guard.** Anything whose game has started, or whose start
   cannot be confirmed, is quarantined and its stake removed.

Two rules run through all of it:

**A blocked card produces no selections, not placeholder ones.** An empty card
that explains itself is useful. A card with invented content is worse than no
card.

**An excluded market is never a pass, an avoid, or a no-value call.** Passes
are genuine model judgements about markets that were priced and modelled. A
market the provider could not supply, or that policy does not allow, is a
different thing, and the two appear in different sections with different
headings.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import (
    BANKROLL_UNIT_DOLLARS,
    MAX_DEFAULT_JUICE,
    MAX_DEFAULT_PRICE,
    MIN_EDGE,
    MIN_PROP_EDGE,
    OUTPUTS_DIR,
)
from nhl_betting_lab.market_eligibility import EligibilityReport
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    implied_to_american,
    is_heavy_juice,
)
from nhl_betting_lab.puck_drop import (
    QUARANTINE_SECTION,
    QuarantineResult,
    apply_puck_drop_guard,
    render_quarantine_section,
)


CARD_MARKDOWN_FILENAME = "gameday_card.md"
CARD_JSON_FILENAME = "gameday_card.json"

BEST_BETS_SECTION = "Best bets"
LEANS_SECTION = "Leans"
PASSES_SECTION = "Passes / notable avoids"

#: Edge at which a selection is a best bet rather than a lean. Leans are
#: recorded and not staked: in the EPL lab the smallest-edge bets lost, which
#: is the expected shape when an edge is mostly estimation error.
BEST_BET_EDGE = 0.09
BEST_BET_PROP_EDGE = 0.12

#: Flat stakes by tier, in units. Small on purpose: these are positions whose
#: expected value is genuinely uncertain, and the sizing should say so.
TIER_UNITS = {"A": 0.5, "B": 0.25, "C": 0.1}

#: Markets that cannot produce a selection without information this lab does
#: not have, whatever the policy says. Stated as data so the card can name the
#: reason rather than silently dropping the market.
HARD_GATED_MARKETS: dict[str, str] = {
    "goalie_saves": (
        "A saves prop is only bettable on the confirmed starter, and starters "
        "are confirmed close to puck drop, after this card is built. This lab "
        "has no confirmed-starter source, so goalie saves cannot produce a "
        "selection. See docs/goalie_props_need_a_confirmed_starter.md. This is "
        "not a judgement that the market has no value."
    )
}


@dataclass
class Candidate:
    """One priced selection with a model opinion behind it."""

    date: str
    commence_time: str
    home_team: str
    away_team: str
    market: str
    selection: str
    player: str
    line: float | None
    american_odds: float
    book: str
    model_probability: float
    implied_probability: float
    edge: float
    fair_american: int
    tier: str
    suggested_units: float
    section: str

    def as_row(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class GamedayCard:
    """Everything the card knows, in a shape a report and a test can read."""

    generated_at: str
    card_generated: bool = False
    slate_games: int = 0
    included_markets: tuple[str, ...] = ()
    excluded_markets: dict[str, str] = field(default_factory=dict)
    best_bets: list[dict[str, Any]] = field(default_factory=list)
    leans: list[dict[str, Any]] = field(default_factory=list)
    passes: list[dict[str, Any]] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    stake_removed_by_guard: float = 0.0
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    safety: dict[str, bool] = field(
        default_factory=lambda: {
            "odds_fabricated": False,
            "bets_placed": False,
            "policy_edited": False,
            "excluded_market_shown_as_a_pass": False,
            "started_game_offered_as_a_play": False,
        }
    )

    @property
    def total_units(self) -> float:
        return sum(
            float(row.get("suggested_units", 0.0) or 0.0) for row in self.best_bets
        )

    def selection_fingerprint(self) -> str:
        """A stable key for "did the selections change since last time".

        Deliberately excludes prices and probabilities. A card whose only
        difference is that a line moved half a cent has not changed its
        selections, and treating it as changed would send an email a day until
        nobody read them.
        """
        keys = sorted(
            f"{row.get('market')}|{row.get('player') or ''}|"
            f"{row.get('home_team')}|{row.get('away_team')}|"
            f"{row.get('selection')}|{row.get('line')}"
            for row in self.best_bets
        )
        return "\n".join(keys)

    def summary_line(self) -> str:
        if not self.card_generated:
            return (
                f"No card. {len(self.blockers)} blocker(s); no selection, "
                "lean, pass, or stake was produced."
            )
        return (
            f"{len(self.best_bets)} best bet(s), {len(self.leans)} lean(s), "
            f"{len(self.passes)} pass(es) across {self.slate_games} game(s); "
            f"{self.total_units:g} unit(s) staked."
        )


def _tier_for(edge: float, is_prop: bool) -> str:
    best_bar = BEST_BET_PROP_EDGE if is_prop else BEST_BET_EDGE
    if edge >= best_bar * 1.5:
        return "A"
    if edge >= best_bar:
        return "B"
    return "C"


def build_candidates(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    min_edge: float = MIN_EDGE,
    min_prop_edge: float = MIN_PROP_EDGE,
    juice_limit: int = MAX_DEFAULT_JUICE,
    max_price: int = MAX_DEFAULT_PRICE,
) -> tuple[list[Candidate], list[Candidate]]:
    """Split priced rows into `(selections, passes)`.

    `probabilities` is keyed by
    `(market, player_casefold, home, away, selection, line)`. A row with no
    key is not a pass — it is a row with no model opinion, and it appears in
    neither list. Passes are genuine judgements about rows the model *did*
    price.
    """
    selections: list[Candidate] = []
    passes: list[Candidate] = []
    if prices.empty:
        return selections, passes

    # Best price per selection. A card that quoted the worst available price
    # would understate every edge; one that quoted a price from a book the
    # reader cannot reach would overstate it. Best-of-what-was-staged is the
    # honest middle, and the book is always named.
    best: dict[tuple, Any] = {}
    for row in prices.itertuples():
        market = str(getattr(row, "market", "")).strip()
        selection = str(getattr(row, "selection", "")).strip().lower()
        player = str(getattr(row, "player", "") or "").strip()
        line_value = getattr(row, "line", None)
        try:
            line = float(line_value) if line_value is not None and not pd.isna(line_value) else None
        except (TypeError, ValueError):
            line = None
        key = (
            market,
            player.casefold(),
            str(getattr(row, "home_team", "")),
            str(getattr(row, "away_team", "")),
            selection,
            line,
        )
        try:
            price = float(getattr(row, "american_odds"))
            american_to_implied(price)
        except (OddsError, TypeError, ValueError):
            continue
        current = best.get(key)
        if current is None or price > float(getattr(current, "american_odds")):
            best[key] = row

    for key, row in best.items():
        market_key, player_key, home, away, selection, line = key
        market = MARKETS_BY_KEY.get(market_key)
        if market is None:
            continue
        probability = probabilities.get(key)
        if probability is None:
            continue
        price = float(getattr(row, "american_odds"))
        implied = american_to_implied(price)
        edge = float(probability) - implied
        bar = min_prop_edge if market.is_prop else min_edge
        candidate = Candidate(
            date=str(getattr(row, "date", "")),
            commence_time=str(getattr(row, "commence_time", "")),
            home_team=home,
            away_team=away,
            market=market_key,
            selection=selection,
            player=str(getattr(row, "player", "") or "").strip(),
            line=line,
            american_odds=price,
            book=str(getattr(row, "book", "")),
            model_probability=float(probability),
            implied_probability=implied,
            edge=edge,
            fair_american=(
                implied_to_american(min(max(float(probability), 1e-4), 1 - 1e-4))
            ),
            tier=_tier_for(edge, market.is_prop),
            suggested_units=0.0,
            section=PASSES_SECTION,
        )

        if edge < bar:
            candidate.section = PASSES_SECTION
            passes.append(candidate)
            continue
        if is_heavy_juice(price, juice_limit):
            candidate.section = PASSES_SECTION
            passes.append(candidate)
            continue
        if price > max_price:
            # An independent-count model overstates rare outcomes and the
            # market's favourite-longshot bias prices them short on top of
            # that. The two errors compound in the same direction.
            candidate.section = PASSES_SECTION
            passes.append(candidate)
            continue

        best_bar = BEST_BET_PROP_EDGE if market.is_prop else BEST_BET_EDGE
        candidate.section = (
            BEST_BETS_SECTION if edge >= best_bar else LEANS_SECTION
        )
        if candidate.section == BEST_BETS_SECTION:
            candidate.suggested_units = TIER_UNITS.get(candidate.tier, 0.1)
        selections.append(candidate)

    selections.sort(key=lambda item: (-item.edge, item.market, item.player))
    passes.sort(key=lambda item: (-item.edge, item.market, item.player))
    return selections, passes


def build_card(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    eligibility: EligibilityReport,
    blockers: Sequence[str] = (),
    now: datetime | None = None,
    juice_limit: int = MAX_DEFAULT_JUICE,
) -> GamedayCard:
    """Assemble the card, or explain why there is not one."""
    moment = now or datetime.now(timezone.utc)
    card = GamedayCard(
        generated_at=moment.isoformat(timespec="seconds"),
        slate_games=eligibility.games_in_slate,
        excluded_markets=dict(eligibility.exclusion_reasons()),
        blockers=list(blockers),
    )

    eligible = [
        market
        for market in eligibility.eligible_markets
        if market not in HARD_GATED_MARKETS
    ]
    for market, reason in HARD_GATED_MARKETS.items():
        if market in eligibility.eligible_markets:
            card.excluded_markets[market] = reason
    card.included_markets = tuple(eligible)

    if not eligible:
        card.blockers.append(
            "No market is eligible for automated picks. Every market is "
            "listed under excluded markets with its reason. None of them is a "
            "pass, an avoid, or a no-value call."
        )

    card.notes = _standing_notes(juice_limit)

    if card.blockers:
        return card

    usable = prices[
        prices["market"].astype(str).str.strip().isin(eligible)
    ].copy()
    selections, passes = build_candidates(
        usable, probabilities, juice_limit=juice_limit
    )

    guarded = apply_puck_drop_guard(
        [item.as_row() for item in selections], now=moment
    )
    card.quarantined = guarded.quarantined
    card.stake_removed_by_guard = guarded.stake_removed

    card.best_bets = [
        row for row in guarded.playable if row["section"] == BEST_BETS_SECTION
    ]
    card.leans = [
        row for row in guarded.playable if row["section"] == LEANS_SECTION
    ]
    # Passes are also checked: a pass on a game that has started is not a
    # useful thing to publish either, and letting one through would mean the
    # guard's coverage depended on which section a row landed in.
    pass_guard = apply_puck_drop_guard(
        [item.as_row() for item in passes], now=moment
    )
    card.passes = pass_guard.playable

    # Defence in depth. The input was already filtered to eligible markets;
    # this catches a future change upstream that lets an excluded one through.
    leaked = sorted(
        {str(row.get("market")) for row in card.best_bets + card.leans}
        - set(eligible)
    )
    if leaked:
        card.blockers.append(
            f"An excluded market reached the selections: {leaked}. No card was "
            "produced."
        )
        card.best_bets = []
        card.leans = []
        card.passes = []
        return card

    card.card_generated = True
    return card


def _standing_notes(juice_limit: int) -> list[str]:
    return [
        "Recommendations only. No bet is placed by this repository, ever.",
        "An excluded market is not a pass, an avoid, or a no-value call. It is "
        "a market that was not usable, for the stated reason, and no price was "
        "invented for it.",
        "A selection whose game has started — or whose start could not be "
        f"confirmed — appears under '{QUARANTINE_SECTION}' with its stake "
        "removed. Ambiguity falls on the not-a-play side.",
        f"Nothing worse than {juice_limit} is selected. Plus-money props and "
        "alternate lines are preferred over forcing a heavy price.",
        "Leans are recorded and not staked. The smallest edges are mostly "
        "estimation error, and in the EPL lab they lost.",
        "No edge here is a demonstrated edge. See "
        "`data/outputs/what_we_can_claim.md` for what the evidence actually "
        "supports.",
    ]


def _price(value: object) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"
    return f"{int(number):+d}" if float(number).is_integer() else f"{number:+.1f}"


def _label(row: Mapping[str, Any]) -> str:
    player = str(row.get("player") or "").strip()
    line = row.get("line")
    selection = str(row.get("selection", ""))
    line_text = "" if line is None or pd.isna(line) else f" {float(line):g}"
    if player:
        return f"{player} {selection}{line_text}".strip()
    return f"{selection}{line_text}".strip()


def _rows_table(rows: Sequence[Mapping[str, Any]], *, staked: bool) -> list[str]:
    header = "| Game | Market | Selection | Model | Edge | Price | Book |"
    divider = "|:-----|:-------|:----------|------:|-----:|------:|:-----|"
    if staked:
        header = (
            "| Game | Market | Selection | Model | Edge | Price | Book | Units |"
        )
        divider = (
            "|:-----|:-------|:----------|------:|-----:|------:|:-----|------:|"
        )
    lines = [header, divider]
    for row in rows:
        game = f"{row.get('away_team', '')} @ {row.get('home_team', '')}".strip(" @")
        cells = (
            f"| {game or '-'} | `{row.get('market', '-')}` | {_label(row)} "
            f"| {float(row.get('model_probability', 0.0)):.1%} "
            f"| {float(row.get('edge', 0.0)):+.1%} "
            f"| {_price(row.get('american_odds'))} "
            f"| {row.get('book') or '-'} |"
        )
        if staked:
            cells += f" {float(row.get('suggested_units', 0.0)):g} |"
        lines.append(cells)
    lines.append("")
    return lines


def render_card(card: GamedayCard) -> str:
    lines = [
        "# NHL gameday card",
        "",
        f"- Generated: {card.generated_at}",
        f"- {card.summary_line()}",
        (
            "- Included markets: **"
            + (", ".join(card.included_markets) or "none")
            + "**"
        ),
        f"- Unit size: ${BANKROLL_UNIT_DOLLARS:g}",
        "",
    ]

    if not card.card_generated:
        lines.extend(
            [
                "## No card",
                "",
                *[f"- {item}" for item in card.blockers],
                "",
                (
                    "**No best bet, lean, pass, or stake was produced.** An "
                    "empty card that explains itself is useful; a card with "
                    "invented content is worse than no card."
                ),
                "",
            ]
        )
    else:
        lines.extend([f"## {BEST_BETS_SECTION}", ""])
        lines.extend(
            _rows_table(card.best_bets, staked=True)
            if card.best_bets
            else ["_No best bets._", ""]
        )
        lines.extend([f"## {LEANS_SECTION}", ""])
        lines.extend(
            _rows_table(card.leans, staked=False)
            if card.leans
            else ["_No leans._", ""]
        )
        lines.extend(
            [
                "Leans are recorded and not staked.",
                "",
                f"## {PASSES_SECTION}",
                "",
            ]
        )
        lines.extend(
            _rows_table(card.passes[:25], staked=False)
            if card.passes
            else ["_No passes._", ""]
        )
        if len(card.passes) > 25:
            lines.extend(
                [
                    f"_{len(card.passes) - 25} further passes not listed._",
                    "",
                ]
            )
        lines.extend(
            [
                (
                    "These are genuine model judgements about markets that "
                    "were priced and modelled. They are **not** the same thing "
                    "as the excluded markets below."
                ),
                "",
            ]
        )

    # The quarantined rows still carry `_removed_units`, so the result object
    # recomputes the removed stake rather than being told it — the rendered
    # total and the rows it lists cannot disagree.
    lines.extend(
        render_quarantine_section(
            QuarantineResult(playable=[], quarantined=card.quarantined)
        )
    )

    lines.extend(["## Excluded markets", ""])
    if card.excluded_markets:
        for market, reason in sorted(card.excluded_markets.items()):
            lines.append(f"- `{market}`: {reason}")
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            (
                "An excluded market is **not** a pass, an avoid, or a no-value "
                "call, and no price was invented for it."
            ),
            "",
            "## Safety",
            "",
            *[
                f"- {label.replace('_', ' ').capitalize()}: "
                f"**{'Yes' if value else 'No'}**"
                for label, value in sorted(card.safety.items())
            ],
            "",
            "## Standing notes",
            "",
            *[f"- {note}" for note in card.notes],
            "",
        ]
    )
    return "\n".join(lines)


def save_card(card: GamedayCard, *, output_dir: Path | None = None) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / CARD_MARKDOWN_FILENAME
    markdown.write_text(render_card(card), encoding="utf-8")
    json_path = directory / CARD_JSON_FILENAME
    payload = dict(card.__dict__)
    payload["selection_fingerprint"] = card.selection_fingerprint()
    payload["total_units"] = card.total_units
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
