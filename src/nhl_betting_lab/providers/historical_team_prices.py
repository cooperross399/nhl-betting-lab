"""Buying historical team-market prices, which are far cheaper than props.

Props are per-event: ten credits per market per event, so one game-day of
twelve games across six markets is 720. Team markets come from the **bulk**
historical endpoint, which returns every game on the board at one instant for
`10 x markets x regions` — sixty credits for the whole slate at the lab's two
regions (`us,us2`), whether that slate is four games or fourteen.

That difference is why the team markets went unmeasured for so long while the
props were bought twice: the props were expensive enough to think about and
the team markets were cheap enough to forget.

Same rules as everywhere else. Real spend is read from `x-requests-last`, the
cap is enforced before each request against both the estimate and the
measured spend, and a snapshot already on disk costs nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import RAW_DIR
from nhl_betting_lab.markets import TEAM_MARKETS
from nhl_betting_lab.providers.odds_api import (
    OddsApiProvider,
    ProviderError,
    normalize_event,
)


CACHE_DIRNAME = "historical_team_prices"

#: The bulk historical endpoint's documented rate, which is the one place the
#: provider is unambiguous: "10 x [markets] x [regions]".
BULK_CREDITS_PER_MARKET_PER_REGION = 10

#: Markets the bulk endpoint serves. The three-way and the alternate ladders
#: are per-event and are deliberately not bought here — asking for them would
#: make the provider refuse the whole request, which is exactly how every live
#: team fetch failed for a week.
BULK_MARKETS: tuple[str, ...] = ("h2h", "spreads", "totals")


@dataclass
class TeamPriceBuy:
    rows: list[dict[str, Any]] = field(default_factory=list)
    snapshots_requested: int = 0
    snapshots_bought: int = 0
    snapshots_from_cache: int = 0
    snapshots_skipped_for_budget: int = 0
    events_priced: int = 0
    credits_spent: int = 0
    credits_remaining: str = ""
    errors: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (
            f"{len(self.rows):,} team price rows from {self.events_priced} "
            f"event(s) across {self.snapshots_bought} bought snapshot(s) and "
            f"{self.snapshots_from_cache} cached one(s); "
            f"{self.credits_spent} credit(s) spent"
            + (
                f", {self.credits_remaining} remaining"
                if self.credits_remaining
                else ""
            )
            + f"; {self.snapshots_skipped_for_budget} skipped for budget."
        )


def estimate_credits(*, snapshots: int, markets: int, regions: int) -> int:
    """The documented bulk rate. Per snapshot, not per event.

    `regions` has no default. It defaulted to 1, and the only caller left it
    out, so the buy was gated at one region while it asked for two.
    """
    return (
        int(snapshots)
        * int(markets)
        * int(regions)
        * BULK_CREDITS_PER_MARKET_PER_REGION
    )


def cost_note(*, snapshots: int, markets: int, regions: int) -> str:
    """The quote a dry run prints before anything is bought.

    `regions` is required: this quote was one region's price for its whole
    life while the buy asked for two, so the number approved before `--live`
    was half the bill (1,200 against 2,400 for the script's own example).
    """
    total = estimate_credits(snapshots=snapshots, markets=markets, regions=regions)
    return (
        f"{snapshots} snapshot(s) x {markets} market(s) x {regions} region(s) "
        f"x {BULK_CREDITS_PER_MARKET_PER_REGION} = **{total:,} credits**. The "
        "bulk endpoint bills per snapshot rather than per event, so a "
        "fourteen-game night costs the same as a four-game one."
    )


def _cache_path(
    snapshot: str, markets: Sequence[str], *, raw_dir: Path | None = None
) -> Path:
    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / CACHE_DIRNAME
    stamp = str(snapshot).replace(":", "").replace("-", "")
    tag = hashlib.sha256(
        ",".join(sorted(markets)).encode("utf-8")
    ).hexdigest()[:8]
    return directory / f"{stamp}_{tag}.json"


def _read_cache(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _write_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def buy_team_prices(
    provider: OddsApiProvider,
    *,
    snapshots: Sequence[str],
    markets: Sequence[str] = BULK_MARKETS,
    credit_cap: int,
    raw_dir: Path | None = None,
) -> TeamPriceBuy:
    """Buy one bulk snapshot per instant, under a hard cap.

    Until 2026-09-25 each snapshot was estimated at
    `estimate_credits(snapshots=1, markets=3)` — one region, 30 credits —
    while the request asked for `provider.regions`, `us,us2` since
    2026-08-28, and was billed 60; and the measured spend was added up and
    never compared with the cap. With a biller charging the documented
    `10 x markets x regions`, a cap of 2,000 over 90 snapshots bought 66 and
    spent 3,960, and the workflow's default cap of 60 spent 120. The
    estimate now carries the provider's region count, and a second gate
    reads what has actually been charged, as `buy_historical_props` does.
    """
    wanted = list(markets)
    if not wanted:
        raise ProviderError("A team-price buy needs at least one market.")
    per_snapshot = estimate_credits(
        snapshots=1, markets=len(wanted), regions=provider.region_count
    )
    buy = TeamPriceBuy(snapshots_requested=len(snapshots))
    worst_case = 0
    # The dearest snapshot the provider has actually charged so far, never
    # below the estimate: the best available forecast of the next charge.
    largest_charge = per_snapshot
    stopped_on_measured = False

    for snapshot in snapshots:
        path = _cache_path(snapshot, wanted, raw_dir=raw_dir)
        payload = _read_cache(path)
        if payload is None:
            if worst_case + per_snapshot > credit_cap:
                buy.snapshots_skipped_for_budget += 1
                continue
            # The gate that cannot be mis-specified: what the provider says
            # it has charged, projected one more snapshot ahead at the
            # dearest charge seen. An estimate can be wrong about the bill;
            # the running total of `x-requests-last` cannot. Skipped, not
            # stopped, so a snapshot already cached further on is still read.
            if buy.credits_spent + largest_charge > credit_cap:
                buy.snapshots_skipped_for_budget += 1
                if not stopped_on_measured:
                    stopped_on_measured = True
                    buy.errors.append(
                        f"Stopped buying at the {credit_cap:,}-credit cap on "
                        f"MEASURED spend ({buy.credits_spent:,} charged; the "
                        f"next snapshot could cost {largest_charge:,})."
                    )
                continue
            try:
                payload, headers = provider._get(  # noqa: SLF001 — one door
                    f"{provider.base_url}/v4/historical/sports/"
                    f"{provider.sport_key}/odds",
                    provider._params(  # noqa: SLF001
                        regions=provider.regions,
                        markets=",".join(wanted),
                        date=str(snapshot),
                    ),
                )
            except ProviderError as exc:
                buy.errors.append(f"{snapshot}: {exc}")
                worst_case += per_snapshot
                continue
            worst_case += per_snapshot
            try:
                measured = int(str(headers.get("x-requests-last", "")).strip())
            except (TypeError, ValueError):
                measured = 0
            charged = measured or per_snapshot
            buy.credits_spent += charged
            largest_charge = max(largest_charge, charged)
            buy.credits_remaining = (
                str(headers.get("x-requests-remaining", ""))
                or buy.credits_remaining
            )
            buy.snapshots_bought += 1
            _write_cache(path, payload)
        else:
            buy.snapshots_from_cache += 1

        data = payload.get("data") if isinstance(payload, Mapping) else payload
        if not isinstance(data, list):
            buy.errors.append(f"{snapshot}: malformed historical payload.")
            continue
        for event in data:
            if not isinstance(event, Mapping):
                continue
            rows = normalize_event(event, fetched_at=str(snapshot))
            if rows:
                buy.events_priced += 1
            for row in rows:
                row["snapshot"] = str(snapshot)
            buy.rows.extend(rows)
    return buy


def bulk_market_keys() -> tuple[str, ...]:
    """Team markets this lab prices that the bulk endpoint actually serves."""
    served = set(BULK_MARKETS)
    return tuple(
        market.provider_key
        for market in TEAM_MARKETS
        if market.provider_key in served
    )
