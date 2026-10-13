"""Prices for the new markets: what is asked, what it costs, and how a response reads.

Cooper approved, on 2026-10-13 ("do it all"), buying past prices for the
markets `nhl_betting_lab.new_markets` models (period markets, power-play
points, faceoffs won, shots, first and last goal scorer) and capturing them
daily, so the shadow models can be backtested against prices that were for
sale. **None of it reaches the card.** These keys are not in `markets.py`, not
in the provider policy, and nothing on the card's path imports this package
(`tests/test_the_shadow_model_cannot_reach_the_card.py`).

## Where the prices live

Every response is cached raw, one file per response, under a prices directory
(`data/raw/new_market_prices` by default, which `.gitignore` covers; the
workflow uses the runner's temp directory). The raw cache is the evidence and
every table is rebuilt from it (`rows_from_cache`), as with the bought props.
The cache is kept in the PRIVATE repository `cooperross399/nhl-closing-lines`,
branch `new-markets` (`scripts/private_new_market_store.py`), and never in
this public repository, an artifact, or a run summary beyond aggregates: The
Odds API's terms forbid redistributing their data as files.

## What it costs

* **Historical** (`/v4/historical/.../events/{id}/odds`): 10 credits per
  market RETURNED per region (measured on the props buy, 2026-08-25). Asking
  `len(markets)` keys at two regions is gated at `10 x len(markets) x 2` an
  event, the pessimistic bound, and charged at `x-requests-last`.
* **Live** (`/v4/sports/.../events/{id}/odds`): 1 credit per market per region
  per event, gated at `len(markets) x 2` and charged at `x-requests-last`.

Every paid loop here is `gated_buy`, which carries the props buy's two gates
(#234): the estimate, and MEASURED spend projected one event ahead at the
dearest charge seen. A run can pass its cap by at most how much the next
charge exceeds the dearest one seen, and any overspend is named in `errors`.

## The keys

`CORE_KEYS` are the provider's own names, as the 2026-09-01 re-probe saw them
served (`docs/periphery_markets_decision.md`). `ALTERNATE_KEYS` follow the
provider's naming for alternate ladders but have **not** been seen served for
NHL; they are asked only on request (`--with-alternates`), and a 422 for the
list falls back once to the core keys, so one unknown key cannot lose every
market. A key nobody quotes costs nothing on the historical endpoint (billed
per market returned).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import RAW_DIR

#: Periods 1-3, regulation only, as `periods.PERIODS`.
PERIODS = (1, 2, 3)

PERIOD_KINDS = ("h2h", "h2h_3_way", "spreads", "totals")
PERIOD_KEYS: tuple[str, ...] = tuple(f"{kind}_p{p}" for kind in PERIOD_KINDS for p in PERIODS)
EXTRA_PROP_KEYS: tuple[str, ...] = (
    "player_power_play_points",
    "player_faceoffs_won",
    "player_shots",
)
SCORER_KEYS: tuple[str, ...] = ("player_goal_scorer_first", "player_goal_scorer_last")
CORE_KEYS: tuple[str, ...] = PERIOD_KEYS + EXTRA_PROP_KEYS + SCORER_KEYS

#: The provider's alternate-ladder naming applied to these markets. Not seen
#: served for NHL; asked only with `--with-alternates`.
ALTERNATE_KEYS: tuple[str, ...] = (
    *(f"alternate_spreads_p{p}" for p in PERIODS),
    *(f"alternate_totals_p{p}" for p in PERIODS),
    "player_power_play_points_alternate",
    "player_faceoffs_won_alternate",
    "player_shots_alternate",
)

#: Measured on the props buy: ten credits per market returned per region.
HISTORICAL_CREDITS_PER_MARKET = 10
#: Live per-event markets: one credit per market per region.
LIVE_CREDITS_PER_MARKET = 1

#: The selection a "no goalscorer" outcome is staged under.
NO_SCORER = "no_scorer"
NO_SCORER_NAMES = frozenset(
    {"no goalscorer", "no goal scorer", "no scorer", "no goal", "no goals", "none"}
)

PRICE_COLUMNS = (
    "provider_event_id",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "family",
    "period",
    "player",
    "selection",
    "line",
    "american_odds",
    "book",
    "snapshot",
    "source",
)

HISTORICAL_DIR = "historical"
LIVE_DIR = "live"

#: Where the raw responses live on a runner or laptop. `data/raw/**` is never
#: committed; the only copy kept anywhere else is the PRIVATE repository
#: (`scripts/private_new_market_store.py`).
DEFAULT_PRICES_DIR = RAW_DIR / "new_market_prices"


def market_family(key: str) -> tuple[str, int]:
    """`(family, period)` for a provider key; period 0 for a whole-game market.

    Families: `h2h`, `h2h_3_way`, `spreads`, `totals` (periods), and
    `power_play_points`, `faceoffs_won`, `shots`, `first_scorer`,
    `last_scorer`. An alternate ladder lands on its featured market's family,
    as the card's alternate props land on theirs. Raises on an unknown key.
    """
    text = str(key).strip().lower()
    match = re.fullmatch(r"(?:alternate_)?(h2h_3_way|h2h|spreads|totals)_p([123])", text)
    if match:
        return match.group(1), int(match.group(2))
    base = text[: -len("_alternate")] if text.endswith("_alternate") else text
    families = {
        "player_power_play_points": "power_play_points",
        "player_faceoffs_won": "faceoffs_won",
        "player_shots": "shots",
        "player_goal_scorer_first": "first_scorer",
        "player_goal_scorer_last": "last_scorer",
    }
    if base in families:
        return families[base], 0
    raise KeyError(f"{key!r} is not a new-market key")


def is_new_market_key(key: object) -> bool:
    try:
        market_family(str(key))
    except KeyError:
        return False
    return True


def _price(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or -100 < price < 100:
        return None
    return price


def _line(outcome: Mapping[str, Any]) -> float | None:
    point = outcome.get("point")
    if point is None:
        return None
    try:
        value = float(point)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _side(name: str, home: str, away: str) -> str | None:
    if name == home:
        return "home"
    if name == away:
        return "away"
    return None


def parse_event(
    event: Mapping[str, Any], *, snapshot: str, source: str
) -> list[dict[str, Any]]:
    """Tidy price rows for the new markets in one event payload.

    Every book's price is kept; a market this module does not know is skipped.
    Selections are in this lab's vocabulary: `home`/`away` (and `draw`) for
    the period moneylines and spreads, `over`/`under` for totals and the
    player counts, `yes`/`no` for a scorer, and `no_scorer` for "no
    goalscorer". A line is required where the market has one and absent where
    it has none; an outcome that does not fit is dropped, never guessed at.
    """
    event_id = str(event.get("id", "")).strip()
    commence = str(event.get("commence_time", "")).strip()
    home = str(event.get("home_team", "")).strip()
    away = str(event.get("away_team", "")).strip()
    if not event_id or not home or not away:
        return []
    rows: list[dict[str, Any]] = []
    for bookmaker in event.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        book = str(bookmaker.get("title") or bookmaker.get("key") or "").strip()
        if not book:
            continue
        for market in bookmaker.get("markets", []) or []:
            if not isinstance(market, Mapping):
                continue
            key = str(market.get("key", "")).strip().lower()
            try:
                family, period = market_family(key)
            except KeyError:
                continue
            for outcome in market.get("outcomes", []) or []:
                if not isinstance(outcome, Mapping):
                    continue
                price = _price(outcome.get("price"))
                if price is None:
                    continue
                name = str(outcome.get("name", "")).strip()
                description = str(outcome.get("description", "") or "").strip()
                lowered = name.lower()
                line = _line(outcome)
                player = ""
                if family in ("h2h", "h2h_3_way"):
                    selection = _side(name, home, away)
                    if selection is None and family == "h2h_3_way" and lowered in {"draw", "tie"}:
                        selection = "draw"
                    if selection is None:
                        continue
                    line = None
                elif family == "spreads":
                    selection = _side(name, home, away)
                    if selection is None or line is None:
                        continue
                elif family == "totals":
                    if lowered not in {"over", "under"} or line is None:
                        continue
                    selection = lowered
                elif family in ("power_play_points", "faceoffs_won", "shots"):
                    if lowered not in {"over", "under"} or line is None or not description:
                        continue
                    selection, player = lowered, description
                else:  # first_scorer / last_scorer
                    line = None
                    if lowered in {"yes", "no"}:
                        if not description:
                            continue
                        if description.lower() in NO_SCORER_NAMES:
                            if lowered == "no":
                                continue
                            selection = NO_SCORER
                        else:
                            selection, player = lowered, description
                    elif lowered in NO_SCORER_NAMES or description.lower() in NO_SCORER_NAMES:
                        selection = NO_SCORER
                    elif name:
                        selection, player = "yes", name
                    else:
                        continue
                rows.append(
                    {
                        "provider_event_id": event_id,
                        "commence_time": commence,
                        "home_team": home,
                        "away_team": away,
                        "market": key,
                        "family": family,
                        "period": period,
                        "player": player,
                        "selection": selection,
                        "line": line,
                        "american_odds": price,
                        "book": book,
                        "snapshot": snapshot,
                        "source": source,
                    }
                )
    return rows


# -- the raw cache ------------------------------------------------------------


def markets_fingerprint(markets: Sequence[str]) -> str:
    """A short tag for the market list a response was asked with, so a later
    run asking for more markets never reads an older, narrower response as
    if the extra markets were not offered."""
    joined = ",".join(sorted(str(item) for item in markets))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:8]


def _stamp(instant: str) -> str:
    return re.sub(r"[^0-9TZ]", "", str(instant))


def historical_path(prices_dir: Path, event_id: str, snapshot: str, markets: Sequence[str]) -> Path:
    return Path(prices_dir) / HISTORICAL_DIR / (
        f"{event_id}_{_stamp(snapshot)}_{markets_fingerprint(markets)}.json"
    )


def live_path(
    prices_dir: Path, league_day: str, event_id: str, captured_at: str, markets: Sequence[str]
) -> Path:
    return Path(prices_dir) / LIVE_DIR / str(league_day) / (
        f"{event_id}_{_stamp(captured_at)}_{markets_fingerprint(markets)}.json"
    )


def read_json(path: Path) -> Any | None:
    if not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _event_of(payload: Any) -> Mapping[str, Any] | None:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    event = data if isinstance(data, Mapping) else payload
    return event if isinstance(event, Mapping) else None


def rows_from_cache(prices_dir: Path, *, source: str = "historical") -> pd.DataFrame:
    """Every cached response under `prices_dir`, parsed. Reads files only.

    `source` is `historical`, `live` or `all`. A historical response's
    snapshot is the provider's own `timestamp` (the instant the prices were
    taken), falling back to the instant asked for; a live one's is the
    capture's `captured_at`.
    """
    root = Path(prices_dir)
    frames: list[dict[str, Any]] = []
    folders = {"historical": [HISTORICAL_DIR], "live": [LIVE_DIR], "all": [HISTORICAL_DIR, LIVE_DIR]}[source]
    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            payload = read_json(path)
            event = _event_of(payload)
            if event is None:
                continue
            if folder == HISTORICAL_DIR:
                snapshot = str(
                    (payload.get("timestamp") if isinstance(payload, Mapping) else "")
                    or (payload.get("requested") if isinstance(payload, Mapping) else "")
                    or ""
                )
            else:
                snapshot = str(payload.get("captured_at", "")) if isinstance(payload, Mapping) else ""
            frames.extend(parse_event(event, snapshot=snapshot, source=folder))
    return pd.DataFrame(frames, columns=list(PRICE_COLUMNS))


def markets_seen(prices_dir: Path, *, source: str = "historical") -> dict[str, Any]:
    """Per asked key, how many cached responses asked for it and carried it.

    Only responses whose payload records the market list it was asked with
    count (`asked`), because a market missing from a request that never
    named it is not evidence of anything.
    """
    root = Path(prices_dir)
    folders = {"historical": [HISTORICAL_DIR], "live": [LIVE_DIR], "all": [HISTORICAL_DIR, LIVE_DIR]}[source]
    asked: dict[str, set[str]] = {}
    seen: dict[str, set[str]] = {}
    books: dict[str, set[str]] = {}
    responses = 0
    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            payload = read_json(path)
            event = _event_of(payload)
            if event is None or not isinstance(payload, Mapping):
                continue
            responses += 1
            event_id = str(event.get("id", ""))
            for key in payload.get("markets_asked") or []:
                asked.setdefault(str(key), set()).add(event_id)
            for bookmaker in event.get("bookmakers", []) or []:
                if not isinstance(bookmaker, Mapping):
                    continue
                for market in bookmaker.get("markets", []) or []:
                    if isinstance(market, Mapping):
                        key = str(market.get("key", "")).strip().lower()
                        if is_new_market_key(key):
                            seen.setdefault(key, set()).add(event_id)
                            books.setdefault(key, set()).add(
                                str(bookmaker.get("key") or bookmaker.get("title") or "")
                            )
    keys = sorted(set(asked) | set(seen))
    return {
        "responses": responses,
        "markets": {
            key: {
                "events_asked": len(asked.get(key, set())),
                "events_seen": len(seen.get(key, set())),
                "books": len(books.get(key, set()) - {""}),
            }
            for key in keys
        },
    }


# -- paying for responses, under a cap ----------------------------------------


@dataclass
class PaidRun:
    """What a capped loop of paid requests asked, bought, and spent."""

    events_requested: int = 0
    events_bought: int = 0
    events_from_cache: int = 0
    events_skipped_for_budget: int = 0
    #: Measured from `x-requests-last`, summed. Not an estimate.
    credits_spent: int = 0
    credits_remaining: str = ""
    #: The charge of each bought event, in order, for the cost projection.
    charges: list[int] = field(default_factory=list)
    paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: One line per event whose request failed, for the caller's exit code.
    failed: list[str] = field(default_factory=list)
    fell_back_to_core: bool = False

    @property
    def credits_per_event(self) -> float | None:
        return self.credits_spent / self.events_bought if self.events_bought else None

    def summary_line(self) -> str:
        rate = self.credits_per_event
        return (
            f"{self.events_bought} event(s) bought and {self.events_from_cache} read from the cache "
            f"of {self.events_requested}; {self.credits_spent} credit(s) actually spent"
            + (f" ({rate:.3g} per event)" if rate is not None else "")
            + (f", {self.credits_remaining} remaining" if self.credits_remaining else "")
            + f"; {self.events_skipped_for_budget} event(s) skipped for budget."
        )


def measured_cost(headers: Mapping[str, str]) -> int:
    """What a request actually cost, from `x-requests-last`; 0 when absent
    (the caller then charges the estimate, the safe direction)."""
    try:
        return int(str(headers.get("x-requests-last", "")).strip())
    except (TypeError, ValueError):
        return 0


#: `(event, markets) -> (payload, headers)`. Raises `ProviderError` (or any
#: exception carrying the provider's message) on failure.
Requester = Callable[[Mapping[str, Any], Sequence[str]], tuple[Any, Mapping[str, str]]]


def gated_buy(
    events: Sequence[Mapping[str, Any]],
    *,
    request: Requester,
    path_for: Callable[[Mapping[str, Any], Sequence[str]], Path],
    wrap: Callable[[Mapping[str, Any], Any, Sequence[str]], Any],
    markets: Sequence[str],
    per_event_estimate: int,
    credit_cap: int,
    core_markets: Sequence[str] | None = None,
) -> PaidRun:
    """Ask each event once, under `credit_cap`, caching every answer.

    The props buy's two gates (#234), checked before every event not already
    on disk:

    1. the pessimistic estimate: an event starts only if the worst case of
       everything asked so far, this one included, fits; a failed request is
       charged at that worst case, because it may still have cost quota;
    2. MEASURED spend, projected one event ahead at the dearest charge seen
       so far (never below the estimate): `spent + dearest > cap` skips.

    Both skip rather than stop, so a cached event further on is still read.
    A cached event costs nothing and passes neither gate. An overspend that
    gets through anyway (a charge that rose past the dearest one seen) is
    named in `errors` with both numbers.

    `credit_cap` is required and must be positive: a cap of 0 once meant no
    cap at all in this lab.

    A request refused with a 422 (the provider rejecting the market LIST) is
    retried once with `core_markets`, and every later event asks the core
    list, so one unknown alternate key cannot lose every market.
    """
    if credit_cap is None or int(credit_cap) <= 0:
        raise ValueError(f"A paid loop needs a positive credit cap; got {credit_cap!r}.")
    if per_event_estimate <= 0:
        raise ValueError("The per-event estimate must be positive.")
    run = PaidRun(events_requested=len(events))
    wanted = list(markets)
    worst_case_spent = 0
    largest_charge = int(per_event_estimate)
    stopped_on_measured = False
    for event in events:
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            run.errors.append(f"Skipped an event with no id: {dict(event)!r}")
            continue
        path = path_for(event, wanted)
        if read_json(path) is not None:
            run.events_from_cache += 1
            run.paths.append(path)
            continue
        if worst_case_spent + per_event_estimate > credit_cap:
            run.events_skipped_for_budget += 1
            continue
        if run.credits_spent + largest_charge > credit_cap:
            run.events_skipped_for_budget += 1
            if not stopped_on_measured:
                stopped_on_measured = True
                run.errors.append(
                    f"Stopped at the {credit_cap:,}-credit cap on MEASURED spend "
                    f"({run.credits_spent:,} charged; the next event could cost {largest_charge:,})."
                )
            continue
        asked = list(wanted)
        try:
            payload, headers = request(event, asked)
        except Exception as exc:  # noqa: BLE001 -- the provider's own message is kept
            worst_case_spent += per_event_estimate
            text = " ".join(str(exc).split())
            if "422" in text and core_markets and list(core_markets) != asked:
                wanted = list(core_markets)
                run.fell_back_to_core = True
                run.errors.append(
                    "The provider refused the market list with a 422, so this run fell "
                    f"back to the core keys and dropped {sorted(set(asked) - set(wanted))}."
                )
                path = path_for(event, wanted)
                if read_json(path) is not None:
                    run.events_from_cache += 1
                    run.paths.append(path)
                    continue
                if (
                    worst_case_spent + per_event_estimate > credit_cap
                    or run.credits_spent + largest_charge > credit_cap
                ):
                    run.events_skipped_for_budget += 1
                    continue
                asked = list(wanted)
                try:
                    payload, headers = request(event, asked)
                except Exception as retry:  # noqa: BLE001
                    worst_case_spent += per_event_estimate
                    text = " ".join(str(retry).split())
                    run.failed.append(f"Event {event_id}: {text}")
                    run.errors.append(f"Event {event_id}: {text}")
                    continue
            else:
                run.failed.append(f"Event {event_id}: {text}")
                run.errors.append(f"Event {event_id}: {text}")
                continue
        worst_case_spent += per_event_estimate
        charged = measured_cost(headers) or per_event_estimate
        run.credits_spent += charged
        run.charges.append(charged)
        largest_charge = max(largest_charge, charged)
        run.credits_remaining = str(headers.get("x-requests-remaining", "")) or run.credits_remaining
        if _event_of(payload) is None:
            run.failed.append(f"Event {event_id}: the response was not a JSON object.")
            run.errors.append(f"Event {event_id}: the response was not a JSON object.")
            continue
        write_json(path, wrap(event, payload, asked))
        run.events_bought += 1
        run.paths.append(path)
    if run.credits_spent > credit_cap:
        run.errors.append(
            f"OVERSPENT: {run.credits_spent:,} credit(s) actually charged against a "
            f"{credit_cap:,}-credit cap. The gates forecast each charge from the estimate "
            "and the dearest one measured, and the provider charged more than that forecast."
        )
    return run


def historical_estimate(markets: int, regions: int) -> int:
    """The per-event gate for a historical response: 10 x markets x regions."""
    return HISTORICAL_CREDITS_PER_MARKET * max(1, int(markets)) * max(1, int(regions))


def live_estimate(markets: int, regions: int) -> int:
    """The per-event gate for a live response: 1 x markets x regions."""
    return LIVE_CREDITS_PER_MARKET * max(1, int(markets)) * max(1, int(regions))


def project_cost(charges: Sequence[int], events: int) -> dict[str, float] | None:
    """A full-buy projection from measured per-event charges.

    The mean charge times `events`, with the range the sampled charges span
    (smallest and dearest times `events`). A forecast, not a bound: retention
    varies across a season, and the cap is still enforced as it is spent.
    """
    if not charges:
        return None
    mean = sum(charges) / len(charges)
    return {
        "sampled_events": len(charges),
        "mean_per_event": mean,
        "projected": mean * events,
        "low": min(charges) * events,
        "high": max(charges) * events,
    }
