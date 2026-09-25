"""The team-price buy gated on one region, was billed for two, and never read its bill.

`historical_team_prices.buy_team_prices` sized each snapshot with
`estimate_credits(snapshots=1, markets=3)`, whose `regions` defaults to 1, so
it gated at 30 credits a snapshot. It then asked for `provider.regions`, which
has been `us,us2` since 2026-08-28, and the bulk historical endpoint bills
`10 x markets x regions` = 60. The measured spend it added up
(`buy.credits_spent`) was never compared with the cap, unlike
`buy_historical_props`, which stops on measured spend. And the free dry run's
`cost_note` quoted the one-region figure, so the number the owner approves
before `--live` was half the bill. Meanwhile `CLAUDE.md` and the
`historical_props.estimate_credits` docstring said this sibling "carried the
factor from the day it was written": its signature did, its only caller did
not.

Found by the failure-shape audit (3 of 3 refuters). Measured with the real
`OddsApiProvider` and a requester that bills `10 x markets x regions` and
makes no network call: cap 2,000 over 90 snapshots bought 66 and spent 3,960;
the Historical Props Purchase workflow's default cap of 60 bought 2 and spent
120; the script docstring's own example (40 snapshots) was quoted at 1,200 and
bills 2,400. 395 of the 475 snapshots in the bought team store carry books
from the `us2` region, so the purchases did ask for both.

What these tests hold:

* the gate prices a snapshot at the provider's own region count: cap 60 buys
  one snapshot at two regions and two at one, cap 2,000 buys 33, and what
  the provider bills stays inside the cap even when it reports no charge;
* a provider that bills above the estimate is stopped on MEASURED spend,
  projected at the largest charge seen, so the run cannot pass the cap, and a
  snapshot already cached is still read after buying stops;
* the dry-run quote is the bill: 2,400 for the docstring's example at
  `us,us2`, 1,200 at `us`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from conftest import FakeResponse
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import historical_team_prices as team
from nhl_betting_lab.providers import odds_api


ENVIRONMENT = {"NHL_ODDS_API_KEY": "k" * 24}


def _event(snapshot: str) -> dict:
    return {
        "id": f"evt-{snapshot}",
        "commence_time": snapshot,
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Toronto Maple Leafs", "price": 150},
                            {"name": "Boston Bruins", "price": -180},
                        ],
                    }
                ],
            }
        ],
    }


class _Billing:
    """The bulk historical endpoint, billing what the provider documents —
    `10 x markets x regions` — plus `surcharge`, and recording every ask.

    `billed` is the provider's side of the ledger, kept here whatever the
    buyer believes it spent; `report=False` withholds `x-requests-last`, so
    the buyer has only its own estimate to go on."""

    def __init__(self, surcharge: int = 0, *, report: bool = True) -> None:
        self.surcharge = surcharge
        self.report = report
        self.asked: list[str] = []
        self.billed = 0

    def __call__(self, url: str, *, params: dict, timeout: float) -> FakeResponse:
        self.asked.append(params["date"])
        markets = len(params["markets"].split(","))
        regions = len(params["regions"].split(","))
        charge = 10 * markets * regions + self.surcharge
        self.billed += charge
        headers = {"x-requests-remaining": "1000000"}
        if self.report:
            headers["x-requests-last"] = str(charge)
        return FakeResponse({"data": [_event(params["date"])]}, headers=headers)


def _snapshots(count: int) -> list[str]:
    from datetime import date, timedelta

    start = date(2024, 10, 8)
    return [
        f"{(start + timedelta(days=7 * index)).isoformat()}T23:00:00Z"
        for index in range(count)
    ]


def _buy(tmp_path: Path, *, regions: str, cap: int, count: int,
         surcharge: int = 0, snapshots: list[str] | None = None,
         report: bool = True):
    billing = _Billing(surcharge, report=report)
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=billing, regions=regions
    )
    buy = team.buy_team_prices(
        provider,
        snapshots=snapshots or _snapshots(count),
        markets=team.BULK_MARKETS,
        credit_cap=cap,
        raw_dir=tmp_path / "raw",
    )
    return buy, billing


def test_the_workflow_default_cap_buys_what_two_regions_afford(
    tmp_path: Path,
) -> None:
    """Historical Props Purchase, mode buy_team: cap 60, weekly snapshots."""
    buy, billing = _buy(tmp_path, regions="us,us2", cap=60, count=28)

    assert billing.billed == buy.credits_spent == 60
    assert buy.snapshots_bought == 1 and len(billing.asked) == 1
    assert buy.snapshots_skipped_for_budget == 27
    # Billed at exactly the documented rate, the estimate alone holds the
    # cap; the measured-spend backstop has nothing to catch.
    assert not any("MEASURED" in error for error in buy.errors), buy.errors


def test_the_estimate_holds_the_cap_when_the_charge_is_not_reported(
    tmp_path: Path,
) -> None:
    """With no `x-requests-last` the buyer books its own estimate, so the
    estimate is the only thing between the cap and the provider's bill."""
    buy, billing = _buy(tmp_path, regions="us,us2", cap=60, count=28,
                        report=False)

    assert billing.billed <= 60, f"the provider billed {billing.billed}"
    assert buy.snapshots_bought == 1


def test_the_findings_2000_cap_over_90_snapshots_holds(tmp_path: Path) -> None:
    buy, billing = _buy(tmp_path, regions="us,us2", cap=2000, count=90)

    assert billing.billed == buy.credits_spent == 1980 <= 2000
    assert buy.snapshots_bought == 33 and len(billing.asked) == 33
    assert buy.snapshots_skipped_for_budget == 57
    assert not any("MEASURED" in error for error in buy.errors), buy.errors


def test_one_region_is_priced_at_one_region(tmp_path: Path) -> None:
    """The factor is the provider's region count, not a constant 2."""
    buy, billing = _buy(tmp_path, regions="us", cap=60, count=28)

    assert buy.credits_spent == 60
    assert buy.snapshots_bought == 2 and len(billing.asked) == 2


def test_a_bill_above_the_estimate_stops_on_measured_spend(
    tmp_path: Path,
) -> None:
    """Billed 90 against an estimate of 60, capped at 250.

    The estimate alone would admit a third snapshot (worst case 180 <= 250)
    and spend 270. Projected at the largest measured charge, 180 + 90 = 270
    is past the cap, so buying stops at 180 — and a snapshot already on disk
    still costs nothing and is still read."""
    snapshots = _snapshots(6)
    cached = snapshots[3]
    path = team._cache_path(cached, list(team.BULK_MARKETS), raw_dir=tmp_path / "raw")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": [_event(cached)]}), encoding="utf-8")

    buy, billing = _buy(tmp_path, regions="us,us2", cap=250, count=6,
                        surcharge=30, snapshots=snapshots)

    assert billing.billed == buy.credits_spent == 180 <= 250
    assert billing.asked == snapshots[:2]
    assert buy.snapshots_bought == 2
    assert buy.snapshots_from_cache == 1
    assert {row["snapshot"] for row in buy.rows} == {*snapshots[:2], cached}
    assert buy.snapshots_skipped_for_budget == 3
    assert any("MEASURED" in error for error in buy.errors), buy.errors


# -- the quote the owner approves ----------------------------------------


def _script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "buy_historical_team_prices.py"
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("regions", "quote"), [("us,us2", "2,400"), ("us", "1,200")]
)
def test_the_dry_run_quotes_what_the_buy_is_billed(
    regions: str, quote: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The script docstring's own example: 40 fortnightly snapshots."""
    monkeypatch.setattr(odds_api, "DEFAULT_REGIONS", regions)
    module = _script()

    code = module.main(["--from", "2024-10-08", "--to", "2026-04-15"])
    out = capsys.readouterr().out

    assert code == 0
    assert f"= **{quote} credits**" in out, out
    assert "40 snapshot(s)" in out
