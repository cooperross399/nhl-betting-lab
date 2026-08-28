"""The Odds API adapter for `icehockey_nhl`. Shadow-only by construction.

What this module does: fetch prices, normalise them into a long-form table,
and write that table into `data/staging/`. What it does not do, ever: decide
anything. The card cannot read `data/staging/` — it reads the card input,
which is built only from markets a reviewed policy allowlists. So a shadow run
can be wrong, incomplete, or surprising without a single pick changing.

## The credential

Read from `NHL_ODDS_API_KEY` in the environment (a GitHub secret in CI, a
gitignored `.env` locally). It is never written to a report, a provenance
file, a staging row, or a log line. Every URL that reaches a report goes
through `redact`, and `tests/test_no_secrets_committed.py` fails the build if
a key shape ever reaches a tracked file.

## What a fetch costs

The bulk endpoint serves `h2h`, `spreads` and `totals` for the whole slate for
a handful of credits. Everything else is per-event: **one credit per market
per event when a book actually quotes it, nothing when none does** — the
alternate ladders ride along for free until the day a book hangs one. The cap
is enforced against the pessimistic bound (every asked market billed), so the
per-event fetch is also filtered to the day's slate; spending the budget on
games four days out was how a 32-event August board starved the nearest nine.

Every entry point states the cost before spending it and takes a hard cap, so
a probe cannot become a bill by accident.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from nhl_betting_lab.config import ODDS_API_SPORT_KEY, STAGING_DIR
from nhl_betting_lab.markets import (
    ALL_MARKETS,
    ALTERNATE_PROVIDER_KEYS,
    ANYTIME_SCORER_LINE,
    PROP_MARKETS,
    SCORER_YES_PROVIDER_KEYS,
    market_for_provider_key,
)
from nhl_betting_lab.providers.env_file import redact
from nhl_betting_lab.season import game_date


API_KEY_ENV = "NHL_ODDS_API_KEY"
API_BASE_URL_ENV = "NHL_ODDS_API_BASE_URL"
DEFAULT_API_BASE_URL = "https://api.the-odds-api.com"

#: Only these hosts. A base URL override is a convenience for testing against
#: a local mock, not a way to point the credential at an arbitrary server.
ALLOWED_API_HOSTS = frozenset(
    {"api.the-odds-api.com", "ipv6-api.the-odds-api.com"}
)

PROVIDER_KEY = "odds_api"
PROVIDER_NAME = "the_odds_api"
PROVIDER_TYPE = "odds_api"

DEFAULT_REGIONS = "us"

#: Markets the bulk endpoint serves for the whole slate at once.
BULK_PROVIDER_MARKETS: tuple[str, ...] = ("h2h", "spreads", "totals")

#: Markets that cost one credit per market per event.
PROP_PROVIDER_MARKETS: tuple[str, ...] = tuple(
    market.provider_key for market in PROP_MARKETS
)

#: Every per-event market, props and team alike. The live per-event fetch
#: requests these: `h2h_3_way` sat outside the prop list, so the market this
#: lab wired end to end was simply never asked for.
PER_EVENT_PROVIDER_MARKETS: tuple[str, ...] = tuple(
    market.provider_key for market in ALL_MARKETS if market.per_event
)

#: Alternate ladders. **Per-event only.** The provider does not serve these on
#: the bulk endpoint and answers the whole request with HTTP 422 when they are
#: asked for there — which took down every team-market fetch, and looked like
#: an off-season for two rounds of debugging because the season genuinely had
#: not started.
#:
#: They are fetched per event instead, never dropped. Losing them would repeat
#: the EPL `total_2_5` mistake exactly: the complete line lives in the
#: alternate ladder, and a market written off after checking only the bulk
#: endpoint is a market written off for the wrong reason.
ALTERNATE_PROVIDER_MARKETS: tuple[str, ...] = tuple(ALTERNATE_PROVIDER_KEYS)

SAFE_RESPONSE_HEADERS = (
    "x-requests-remaining",
    "x-requests-used",
    "x-requests-last",
)

STAGING_PRICES_FILENAME = "odds_api_prices_staging.csv"
STAGING_PROPS_FILENAME = "player_props_staging.csv"
PROVENANCE_FILENAME = "staging_provenance.json"

PRICE_COLUMNS = (
    "date",
    "commence_time",
    "provider_event_id",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "line",
    "american_odds",
    "book",
    "fetched_at",
)

Requester = Callable[..., Any]


class ProviderError(RuntimeError):
    """The provider could not answer safely. No staging file is written."""


class MissingCredentialError(ProviderError):
    """A live fetch was asked for without a credential."""


class EmptySlateError(ProviderError):
    """There are no NHL games to price. Not a fault.

    The provider answers the bulk odds endpoint with HTTP 422 when a sport has
    nothing on the board, which is the ordinary state of `icehockey_nhl` from
    mid-June to early October. Treating that as a failure would mail an
    alarming red run every single day of the off-season, and a red that fires
    daily for four months is a red nobody reads in October.

    A 422 is only ever reported as an empty slate after the free events
    endpoint confirms the board really is empty. The same status can mean a
    malformed request, and quietly reading "your markets parameter is wrong"
    as "the season has not started" would hide a real bug for months.
    """


def _default_requester(url: str, **kwargs: Any) -> Any:
    return requests.get(url, **kwargs)


def american_price(value: object) -> float | None:
    """A usable American price, or None. Never a guess."""
    if isinstance(value, bool):
        return None
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or -100 < price < 100:
        return None
    return price


def _line_of(outcome: Mapping[str, Any]) -> float | None:
    point = outcome.get("point")
    if point is None:
        return None
    try:
        return float(point)
    except (TypeError, ValueError):
        return None


@dataclass
class FetchResult:
    """What one fetch saw and what it cost."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    events_seen: int = 0
    events_priced: int = 0
    credits_spent: int = 0
    quota_remaining: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fetched_at: str = ""

    def summary_line(self) -> str:
        return (
            f"{len(self.rows)} price rows from {self.events_priced} of "
            f"{self.events_seen} events; about {self.credits_spent} credit(s) "
            f"spent"
            + (
                f"; {self.quota_remaining} remaining."
                if self.quota_remaining
                else "."
            )
        )


def normalize_event(
    event: Mapping[str, Any], *, fetched_at: str
) -> list[dict[str, Any]]:
    """Long-form price rows for one event payload.

    Every book's price is kept. The card quotes the best reachable book, so
    the staged data has to hold them all; keeping only the best here would
    make "the best price" mean "the best price at the moment of the fetch",
    which is not recoverable afterwards.

    A market this lab does not price is skipped rather than raising. A
    provider response legitimately carries dozens of markets we ignore, and
    treating each as an error would make an ordinary response unparseable.
    """
    event_id = str(event.get("id", "")).strip()
    commence = str(event.get("commence_time", "")).strip()
    home = str(event.get("home_team", "")).strip()
    away = str(event.get("away_team", "")).strip()
    if not home or not away:
        return []

    rows: list[dict[str, Any]] = []
    for bookmaker in event.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        book = str(bookmaker.get("title") or bookmaker.get("key") or "").strip()
        for market in bookmaker.get("markets", []) or []:
            if not isinstance(market, Mapping):
                continue
            provider_key = str(market.get("key", "")).strip().lower()
            target = market_for_provider_key(provider_key)
            if target is None:
                continue
            for outcome in market.get("outcomes", []) or []:
                if not isinstance(outcome, Mapping):
                    continue
                price = american_price(outcome.get("price"))
                if price is None:
                    continue
                name = str(outcome.get("name", "")).strip()
                if not name:
                    continue
                player = str(outcome.get("description", "")).strip()
                selection = name.strip().lower()
                line_value = _line_of(outcome)
                if provider_key in SCORER_YES_PROVIDER_KEYS:
                    # Scorer markets invert the prop shape: the outcome NAME
                    # is the player and the price is the "yes" side, with no
                    # line. Both observed layouts are accepted — name=player,
                    # or name=Yes/No with the player in the description —
                    # and everything lands as goals over 0.5, which is what
                    # an anytime scorer is.
                    if selection in {"yes", "no"}:
                        if not player:
                            continue
                    else:
                        player, selection = name, "yes"
                    line_value = ANYTIME_SCORER_LINE
                if target.is_prop and not player:
                    # A prop outcome with no player is unusable: it cannot be
                    # settled and cannot be matched to a model opinion.
                    continue
                if not target.is_prop and target.key == "team_total":
                    # Both teams arrive under one provider key, the side in
                    # the outcome's description and Over/Under in its name.
                    # Staged in this lab's vocabulary (`home_over` …), for
                    # the same reason the 3-way is: rows staged in the
                    # provider's vocabulary silently miss every join.
                    if selection not in {"over", "under"}:
                        continue
                    if player == home:
                        selection = f"home_{selection}"
                    elif player == away:
                        selection = f"away_{selection}"
                    else:
                        continue
                    player = ""
                if not target.is_prop and target.key == "moneyline":
                    if name == home:
                        selection = "home"
                    elif name == away:
                        selection = "away"
                    else:
                        # NHL moneylines have no draw. An outcome that is
                        # neither team is not something to guess at.
                        continue
                elif not target.is_prop and target.key == "regulation_3_way":
                    # The fourth join-vocabulary bug's fix: the provider names
                    # the sides after the teams and this lab's vocabulary is
                    # home/draw/away, and a row staged in the provider's
                    # vocabulary silently misses every downstream join.
                    if name == home:
                        selection = "home"
                    elif name == away:
                        selection = "away"
                    elif name.strip().lower() in {"draw", "tie"}:
                        selection = "draw"
                    else:
                        continue
                elif not target.is_prop and target.key == "puck_line":
                    if name == home:
                        selection = "home"
                    elif name == away:
                        selection = "away"
                    else:
                        continue
                rows.append(
                    {
                        "date": commence[:10],
                        "commence_time": commence,
                        "provider_event_id": event_id,
                        "home_team": home,
                        "away_team": away,
                        "market": target.key,
                        "player": player,
                        "selection": selection,
                        "line": line_value,
                        "american_odds": price,
                        "book": book,
                        "fetched_at": fetched_at,
                    }
                )
    return rows


class OddsApiProvider:
    """Fetches NHL prices into staging. Decides nothing."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        requester: Requester | None = None,
        sport_key: str = ODDS_API_SPORT_KEY,
        regions: str = DEFAULT_REGIONS,
        bookmakers: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.requester = requester or _default_requester
        self.sport_key = (sport_key or ODDS_API_SPORT_KEY).strip()
        self.regions = (regions or DEFAULT_REGIONS).strip()
        self.bookmakers = str(bookmakers or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self._validate_configuration()

    # -- configuration ---------------------------------------------------

    @property
    def api_key(self) -> str:
        return self.environment.get(API_KEY_ENV, "").strip()

    @property
    def base_url(self) -> str:
        return (
            self.environment.get(API_BASE_URL_ENV, DEFAULT_API_BASE_URL).strip()
            or DEFAULT_API_BASE_URL
        ).rstrip("/")

    def _validate_configuration(self) -> None:
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_API_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderError(
                f"{API_BASE_URL_ENV} must be an approved The Odds API HTTPS "
                "host. The credential is not sent anywhere else."
            )
        if not re.fullmatch(r"[a-z0-9_]+", self.sport_key):
            raise ProviderError("The sport key contains unsafe characters.")
        for label, value in (
            ("regions", self.regions),
            ("bookmakers", self.bookmakers),
        ):
            if value and not re.fullmatch(r"[a-z0-9_,]+", value):
                raise ProviderError(
                    f"Provider {label} must contain only lowercase keys and "
                    "commas."
                )
        if self.timeout_seconds <= 0:
            raise ProviderError("Provider timeout must be positive.")

    def public_configuration(self) -> dict[str, Any]:
        """Everything about this run that is safe to write into a report."""
        return {
            "provider_key": PROVIDER_KEY,
            "provider_name": PROVIDER_NAME,
            "provider_type": PROVIDER_TYPE,
            "sport_key": self.sport_key,
            "regions": self.regions,
            "bookmakers": self.bookmakers or "provider region default",
            "base_url": self.base_url,
            "credential_environment_variable": API_KEY_ENV,
            "credential_present": bool(self.api_key),
        }

    # -- requests --------------------------------------------------------

    def _params(self, **extra: str) -> dict[str, str]:
        params = {
            "apiKey": self.api_key,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if self.bookmakers:
            params["bookmakers"] = self.bookmakers
        params.update(extra)
        return params

    def _get(self, url: str, params: Mapping[str, str]) -> tuple[Any, dict[str, str]]:
        try:
            response = self.requester(
                url, params=dict(params), timeout=self.timeout_seconds
            )
        except (requests.RequestException, OSError, TimeoutError) as exc:
            raise ProviderError(
                redact(
                    f"The odds provider could not be reached "
                    f"({type(exc).__name__}). No staging file was written."
                )
            ) from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status != 200:
            raise ProviderError(
                f"The odds provider returned HTTP {status or 'unknown'}. "
                "No staging file was written."
            )
        try:
            payload = response.json()
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProviderError(
                "The odds provider returned unreadable JSON."
            ) from exc
        headers = getattr(response, "headers", {}) or {}
        safe = {
            name: str(headers.get(name, ""))
            for name in SAFE_RESPONSE_HEADERS
            if headers.get(name) is not None
        }
        return payload, safe

    def _require_credential(self) -> None:
        if not self.api_key:
            raise MissingCredentialError(
                f"A live fetch requires `{API_KEY_ENV}` from the environment, "
                "a gitignored local `.env`, or a GitHub Secret. Never pass the "
                "key as a command argument and never commit it."
            )

    # -- fetches ---------------------------------------------------------

    def list_events(self) -> list[dict[str, Any]]:
        """The upcoming slate. Free: the events list costs no credits."""
        self._require_credential()
        payload, _ = self._get(
            f"{self.base_url}/v4/sports/{self.sport_key}/events",
            {"apiKey": self.api_key, "dateFormat": "iso"},
        )
        if not isinstance(payload, list):
            raise ProviderError("The events list is not a JSON list.")
        return [item for item in payload if isinstance(item, dict)]

    def fetch_team_markets(
        self,
        *,
        fetched_at: str = "",
        league_days: Sequence[str] | None = None,
    ) -> FetchResult:
        """Bulk team markets for the whole slate.

        Cheap: the bulk endpoint bills per market requested, not per event.

        `league_days` must be the **same window the per-event fetch uses**.
        The eligibility gate measures each market's coverage against the
        slate the staged prices describe, so a bulk fetch covering the whole
        posted board while the per-event fetch covers one day would make
        every prop read "priced for 9 of 32 games" — INCOMPLETE, excluded,
        and indistinguishable from books not posting props at all. One
        window over both keeps that measure honest.

        Only the markets the bulk endpoint actually serves are requested. The
        alternate ladders are per-event and asking for them here makes the
        provider refuse the entire request, which is not obvious from the
        response — a 422 with no indication of which market caused it.
        """
        self._require_credential()
        stamp = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        markets = list(BULK_PROVIDER_MARKETS)
        try:
            payload, headers = self._get(
                f"{self.base_url}/v4/sports/{self.sport_key}/odds",
                self._params(regions=self.regions, markets=",".join(markets)),
            )
        except ProviderError as exc:
            if "422" not in str(exc):
                raise
            # A 422 means one of two things and they need separating.
            #
            # Either the provider has no odds for this sport right now — the
            # ordinary state from mid-June until books post opening-night
            # markets — or the request itself was malformed, most likely a
            # market key this adapter asked for and the provider does not
            # serve.
            #
            # The events list does not separate them: through September the
            # October schedule is listed while no book has priced anything, so
            # "events exist" is true in exactly the case being tested for.
            # What separates them is asking again for `h2h` alone, which is
            # the one market every sport serves. If that is refused too, there
            # are no odds. If it succeeds, the market list was the problem.
            try:
                self._get(
                    f"{self.base_url}/v4/sports/{self.sport_key}/odds",
                    self._params(regions=self.regions, markets="h2h"),
                )
            except ProviderError:
                raise EmptySlateError(
                    "The provider is serving no NHL odds at all — even a "
                    "plain moneyline request is refused — so there is nothing "
                    "to price. That is the ordinary state between the end of "
                    "one season and the day books post the next, and it is "
                    "not a fault."
                ) from exc
            raise ProviderError(
                "The provider refused this market list but served a plain "
                f"moneyline request, so one of {markets} is not a market it "
                "serves for this sport. This is a request problem, not an "
                "off-season."
            ) from exc

        if not isinstance(payload, list):
            raise ProviderError("The odds response is not a JSON event list.")
        result = FetchResult(
            fetched_at=stamp,
            events_seen=len(payload),
            credits_spent=len(markets),
            quota_remaining=headers.get("x-requests-remaining", ""),
        )
        events = [item for item in payload if isinstance(item, dict)]
        if league_days is not None:
            allowed_days = {str(day).strip() for day in league_days}
            in_window = [
                event
                for event in events
                if game_date(event.get("commence_time")) in allowed_days
            ]
            if events and not in_window:
                # The board is full of future games and none is today's. That
                # is an ordinary off-day — the league plays most nights, not
                # every night — and it reads exactly like the off-season to
                # everything downstream, which is the correct handling: no
                # card, no fault, no red run.
                raise EmptySlateError(
                    f"The provider lists {len(events)} upcoming NHL game(s) "
                    f"but none is scheduled on {sorted(allowed_days)}, so "
                    "there is nothing to price today. Not a fault."
                )
            outside = len(events) - len(in_window)
            if outside:
                result.warnings.append(
                    f"{outside} posted event(s) fall outside the fetch "
                    f"window {sorted(allowed_days)}. Their markets are "
                    "absent, not empty; the run on their own game day "
                    "fetches them."
                )
            result.events_seen = len(in_window)
            events = in_window
        for event in events:
            rows = normalize_event(event, fetched_at=stamp)
            if rows:
                result.events_priced += 1
                result.rows.extend(rows)
        if not result.rows:
            result.warnings.append(
                "The provider returned events but no usable team-market "
                "prices. Nothing was guessed; the markets stay absent."
            )
        return result

    def estimate_prop_credits(
        self, *, events: int, markets: Sequence[str] | None = None
    ) -> int:
        """One credit per market per event. Stated before it is spent."""
        count = len(list(markets)) if markets is not None else len(PROP_PROVIDER_MARKETS)
        return int(events) * count

    def fetch_player_props(
        self,
        *,
        markets: Sequence[str] | None = None,
        max_events: int = 0,
        credit_cap: int = 0,
        fetched_at: str = "",
        league_days: Sequence[str] | None = None,
    ) -> FetchResult:
        """Per-event player props, under a hard credit cap.

        `credit_cap` is not advisory. A probe that quietly turned into a
        full-slate fetch is exactly the accident this parameter exists to make
        impossible, so the loop stops the moment the next event would exceed
        it — and says how many events it skipped.

        `league_days` restricts the fetch to events on those NHL game dates
        (America/New_York). The board holds every posted upcoming game — 32
        of them one August evening — and the cap spends front-to-back, so an
        unfiltered fetch starves today's slate to buy prices for games days
        away that tomorrow's run will fetch again anyway. None means no
        filter, which is what a probe wants and a daily card must not use.
        """
        self._require_credential()
        stamp = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        wanted = list(markets) if markets is not None else list(PROP_PROVIDER_MARKETS)
        if not wanted:
            raise ProviderError("A props fetch needs at least one market.")
        per_event = len(wanted)

        events = self.list_events()
        result = FetchResult(fetched_at=stamp, events_seen=len(events))
        if league_days is not None:
            allowed_days = {str(day).strip() for day in league_days}
            in_window = [
                event
                for event in events
                if game_date(event.get("commence_time")) in allowed_days
            ]
            outside = len(events) - len(in_window)
            if outside:
                result.warnings.append(
                    f"{outside} posted event(s) fall outside the fetch "
                    f"window {sorted(allowed_days)} and were not asked "
                    "about. Their markets are absent, not empty; the run on "
                    "their own game day fetches them."
                )
            events = in_window
        selected = events[:max_events] if max_events else events

        skipped_for_budget = 0
        for event in selected:
            event_id = str(event.get("id", "")).strip()
            if not event_id:
                continue
            if credit_cap and result.credits_spent + per_event > credit_cap:
                skipped_for_budget += 1
                continue
            try:
                payload, headers = self._get(
                    f"{self.base_url}/v4/sports/{self.sport_key}/events/"
                    f"{event_id}/odds",
                    self._params(regions=self.regions, markets=",".join(wanted)),
                )
            except ProviderError as exc:
                # One event failing must not lose the rest. A partial props
                # result surfaces as an incomplete market, never as a
                # fabricated one.
                result.errors.append(f"Event {event_id}: {exc}")
                continue
            result.credits_spent += per_event
            if headers.get("x-requests-remaining"):
                result.quota_remaining = headers["x-requests-remaining"]
            if not isinstance(payload, Mapping):
                result.errors.append(f"Event {event_id}: malformed payload.")
                continue
            rows = normalize_event(payload, fetched_at=stamp)
            if rows:
                result.events_priced += 1
                result.rows.extend(rows)

        if skipped_for_budget:
            result.warnings.append(
                f"{skipped_for_budget} event(s) were not fetched because the "
                f"{credit_cap}-credit cap would have been exceeded. Their "
                "markets are absent, not empty."
            )
        return result


def to_frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """A long-form price table with the fixed column order."""
    frame = pd.DataFrame(list(rows), columns=list(PRICE_COLUMNS))
    if frame.empty:
        return frame
    return frame.sort_values(
        ["date", "home_team", "market", "player", "selection", "book"],
        ignore_index=True,
    )


def write_staging(
    rows: Sequence[Mapping[str, Any]],
    *,
    filename: str,
    staging_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a staging CSV. Refuses to replace evidence by accident."""
    directory = Path(staging_dir) if staging_dir else Path(STAGING_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if target.exists() and not overwrite:
        raise ProviderError(
            f"{target.name} already exists. Review it first; pass overwrite "
            "only for an intentional replacement."
        )
    to_frame(rows).to_csv(target, index=False, lineterminator="\n")
    return target


def write_provenance(
    result: FetchResult,
    *,
    configuration: Mapping[str, Any],
    staging_files: Sequence[Path],
    staging_dir: Path | None = None,
) -> Path:
    """Record what ran, when, and against what. Never records a credential."""
    directory = Path(staging_dir) if staging_dir else Path(STAGING_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / PROVENANCE_FILENAME
    payload = {
        "generated_at": result.fetched_at,
        "provider": dict(configuration),
        "events_seen": result.events_seen,
        "events_priced": result.events_priced,
        "credits_spent": result.credits_spent,
        "quota_remaining": result.quota_remaining,
        "rows": len(result.rows),
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "staging_files": [str(path.name) for path in staging_files],
        "shadow_only": True,
        "note": (
            "Staging is invisible to the card. Nothing here allowlists a "
            "provider or a market; that requires a reviewed human approval."
        ),
    }
    # Belt and braces: nothing is supposed to put a credential in here, and
    # this makes a mistake in that direction non-fatal.
    text = redact(json.dumps(payload, indent=2, sort_keys=True))
    target.write_text(text + "\n", encoding="utf-8")
    return target
