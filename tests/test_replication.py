from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.reports import replication as rep
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE


def _window(**markets: dict) -> dict:
    return {"by_market": markets}


def _result(bets: int, roi: float, survives: bool) -> dict:
    return {"bets": bets, "roi": roi, "survives_correction": survives}


def _compare(discovery: dict, test: dict) -> rep.ReplicationReport:
    return rep.compare(
        discovery, test, discovery_label="2025-26", test_label="2024-25"
    )


def test_a_result_that_holds_in_the_same_direction_replicates() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.121, True)),
    )
    shots = report.markets[0]

    assert shots.state == rep.REPLICATED
    assert report.replicated_markets == ("shots_on_goal",)


def test_replication_is_still_described_as_two_windows() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.121, True)),
    )

    assert "still two windows" in report.headline()


def test_a_test_window_pointing_the_other_way_contradicts() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, -0.09, False)),
    )
    shots = report.markets[0]

    assert shots.state == rep.CONTRADICTED
    assert NO_DEMONSTRATED_EDGE.capitalize() in shots.reason


def test_merely_not_contradicting_is_not_confirmation() -> None:
    """Most windows fail to contradict most things."""
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.04, False)),
    )
    shots = report.markets[0]

    assert shots.state == rep.NOT_CONFIRMED
    assert "not confirmation" in shots.reason
    assert NO_DEMONSTRATED_EDGE.capitalize() in shots.reason


def test_a_thin_test_window_is_untestable_rather_than_failed() -> None:
    """Calling this a failure is the same over-reading in the other direction."""
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(40, -0.20, False)),
    )
    shots = report.markets[0]

    assert shots.state == rep.UNTESTABLE
    assert "below the" in shots.reason


def test_a_market_that_never_survived_has_nothing_to_replicate() -> None:
    report = _compare(
        _window(points=_result(137, -0.164, False)),
        _window(points=_result(200, -0.05, False)),
    )
    points = report.markets[0]

    assert points.state == rep.UNTESTABLE
    assert "no result here to replicate" in points.reason


def test_with_nothing_discovered_the_headline_says_so() -> None:
    report = _compare(
        _window(points=_result(137, -0.164, False)),
        _window(points=_result(200, -0.05, False)),
    )

    assert "no result to replicate" in report.headline()
    assert "not a failure of the test window" in report.headline()


def test_a_failure_to_replicate_is_stated_without_overclaiming() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.04, False)),
    )

    headline = report.headline()

    assert "did **not** replicate" in headline
    assert NO_DEMONSTRATED_EDGE in headline
    assert "worthless" not in headline


def test_the_two_windows_are_never_pooled() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.121, True)),
    )

    rendered = rep.render_replication(report)

    assert "never pooled here" in rendered
    assert "reads like confirmation" in rendered


def test_a_market_present_in_only_one_window_is_still_reported() -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(points=_result(200, -0.05, False)),
    )

    assert {item.market for item in report.markets} == {"shots_on_goal", "points"}


def test_direction_is_compared_on_sign_not_size() -> None:
    entry = rep.MarketReplication(
        market="x", discovery_bets=100, discovery_roi=0.18,
        discovery_survived=True, test_bets=100, test_roi=0.01,
        test_survived=False, state=rep.NOT_CONFIRMED, reason="",
    )

    assert entry.same_direction is True


def test_a_missing_roi_is_not_treated_as_agreement() -> None:
    entry = rep.MarketReplication(
        market="x", discovery_bets=100, discovery_roi=None,
        discovery_survived=True, test_bets=100, test_roi=0.01,
        test_survived=True, state=rep.UNTESTABLE, reason="",
    )

    assert entry.same_direction is False


def test_saving_writes_both_files(tmp_path: Path) -> None:
    report = _compare(
        _window(shots_on_goal=_result(263, 0.181, True)),
        _window(shots_on_goal=_result(240, 0.121, True)),
    )

    paths = rep.save_replication(report, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert Path(paths["markdown"]).name == "replication.md"
    assert payload["replicated_markets"] == ["shots_on_goal"]


def test_an_unreadable_backtest_file_loads_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ nope", encoding="utf-8")

    assert rep.load_backtest(path) == {}
    assert rep.load_backtest(tmp_path / "absent.json") == {}


def test_the_script_refuses_to_compare_missing_windows(
    tmp_path: Path, capsys
) -> None:
    from test_scripts import load_script

    module = load_script("run_replication.py")

    code = module.main(
        [
            "--discovery", str(tmp_path / "a.json"),
            "--test", str(tmp_path / "b.json"),
            "--output-dir", str(tmp_path),
        ]
    )

    assert code == 1
    assert "missing or unreadable" in capsys.readouterr().out
