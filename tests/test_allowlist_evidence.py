from __future__ import annotations

import json
from pathlib import Path


from nhl_betting_lab.reports import allowlist_evidence as ev


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _all_evidence_present(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in ev.EVIDENCE_FILENAMES:
        (directory / name).write_text(f"# {name}\n", encoding="utf-8")


def test_missing_evidence_blocks_any_recommendation(tmp_path: Path) -> None:
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    assert "Enable nothing yet" in bundle.recommendation()
    assert bundle.missing_files


def test_a_missing_file_is_listed_rather_than_omitted(tmp_path: Path) -> None:
    """A bundle that hides a gap is worse than one that shows it."""
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    rendered = ev.render_bundle(bundle)

    assert "**missing**" in rendered
    assert "listed rather than omitted" in rendered


def test_with_no_price_evidence_nothing_is_supported(tmp_path: Path) -> None:
    _all_evidence_present(tmp_path)

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    assert bundle.supported_markets == ()
    assert "supports enabling nothing" in bundle.recommendation()


def test_calibration_alone_never_supports_a_market(tmp_path: Path) -> None:
    """The confusion this whole project exists to avoid."""
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "props_calibration.json",
        {"markets": [{"market": "shots_on_goal", "samples": 493384}]},
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    shots = next(v for v in bundle.verdicts if v.market == "shots_on_goal")

    assert shots.supported is False
    assert "can never rule it in" in shots.reason


def test_an_interval_including_zero_is_not_supported(tmp_path: Path) -> None:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE

    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 900,
                    "roi": 0.06,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            }
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    points = next(v for v in bundle.verdicts if v.market == "points")

    assert points.supported is False
    assert NO_DEMONSTRATED_EDGE.capitalize() in points.reason


def test_a_thin_sample_is_not_supported_however_good_it_looks(
    tmp_path: Path,
) -> None:
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "goals": {
                    "bets": 40,
                    "roi": 0.55,
                    "includes_zero": False,
                    "survives_correction": True,
                }
            }
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    goals = next(v for v in bundle.verdicts if v.market == "goals")

    assert goals.supported is False
    assert "below the" in goals.reason
    assert "385" in goals.reason


def test_a_large_sample_excluding_zero_is_supported_but_hedged(
    tmp_path: Path,
) -> None:
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "shots_on_goal": {
                    "bets": 1400,
                    "roi": 0.08,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                }
            }
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    assert bundle.supported_markets == ("shots_on_goal",)
    assert "not a recommendation to do so" in bundle.recommendation()
    assert "The decision is yours" in bundle.recommendation()
    assert "has not been replicated" in bundle.recommendation()


def test_a_team_market_is_read_from_its_own_report(tmp_path: Path) -> None:
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "team_markets_measurement.json",
        {
            "markets": [
                {
                    "market": "moneyline",
                    "bets": 800,
                    "roi": 0.04,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            ]
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    moneyline = next(v for v in bundle.verdicts if v.market == "moneyline")

    assert moneyline.bets == 800
    assert moneyline.supported is False


def test_every_present_file_is_checksummed(tmp_path: Path) -> None:
    """The checksums are what make an approval current."""
    _all_evidence_present(tmp_path)

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    present = [item for item in bundle.files if item.present]
    assert present
    assert all(len(item.checksum_sha256) == 64 for item in present)


def test_the_bundle_never_writes_a_receipt(tmp_path: Path) -> None:
    """Not a file, not a draft, not a template with blanks."""
    _all_evidence_present(tmp_path)
    receipts = tmp_path / "data" / "manual" / "human_acceptance_receipts"

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    ev.save_bundle(bundle, output_dir=tmp_path)

    assert not receipts.exists()


def test_the_bundle_says_claude_stops_here(tmp_path: Path) -> None:
    _all_evidence_present(tmp_path)

    rendered = ev.render_bundle(
        ev.build_bundle(
            provider_name="the_odds_api",
            output_dir=tmp_path,
            repository_root=tmp_path,
        )
    )

    assert "Claude does not write one" in rendered
    assert "never writes a human acceptance receipt" in rendered
    assert "Write the receipt yourself" in rendered


def test_the_bundle_gives_the_checksums_a_receipt_must_cite(
    tmp_path: Path,
) -> None:
    _all_evidence_present(tmp_path)
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    rendered = ev.render_bundle(bundle)

    assert '"approved_markets": [' in rendered
    assert '"checksum_sha256"' in rendered
    for item in bundle.files:
        if item.present:
            assert item.checksum_sha256 in rendered


def test_the_bundle_says_approval_skips_no_other_gate(tmp_path: Path) -> None:
    _all_evidence_present(tmp_path)

    rendered = ev.render_bundle(
        ev.build_bundle(
            provider_name="the_odds_api",
            output_dir=tmp_path,
            repository_root=tmp_path,
        )
    )

    assert "does not skip any other gate" in rendered
    assert "puck-drop guard" in rendered


def test_approving_against_the_recommendation_is_named_as_legitimate(
    tmp_path: Path,
) -> None:
    """It happened in the EPL lab, and the record is why that answer is honest."""
    _all_evidence_present(tmp_path)

    rendered = ev.render_bundle(
        ev.build_bundle(
            provider_name="the_odds_api",
            output_dir=tmp_path,
            repository_root=tmp_path,
        )
    )

    assert "against this evidence's recommendation is a" in rendered
    assert "legitimate decision" in rendered


def test_saving_writes_both_files(tmp_path: Path) -> None:
    _all_evidence_present(tmp_path)
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    paths = ev.save_bundle(bundle, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert Path(paths["markdown"]).name == "allowlist_evidence_bundle.md"
    assert payload["supported_markets"] == []


def test_a_malformed_measurement_file_does_not_crash_the_bundle(
    tmp_path: Path,
) -> None:
    _all_evidence_present(tmp_path)
    (tmp_path / "player_props_backtest.json").write_text("{broken", encoding="utf-8")

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    assert bundle.verdicts
    assert ev.render_bundle(bundle)


def test_a_result_that_does_not_survive_the_search_is_not_supported(
    tmp_path: Path,
) -> None:
    """Several markets measured on one body of data; the uncorrected number
    for whichever cleared 95% describes a search."""
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 900,
                    "roi": -0.16,
                    "includes_zero": False,
                    "survives_correction": False,
                    "looks": 7,
                    "adjusted_low": -0.39,
                    "adjusted_high": 0.06,
                }
            }
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    points = next(v for v in bundle.verdicts if v.market == "points")

    assert points.supported is False
    assert "Corrected for the 7 markets" in points.reason
    assert "includes zero" in points.reason


def test_a_supported_market_still_says_it_is_not_replicated(
    tmp_path: Path,
) -> None:
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "shots_on_goal": {
                    "bets": 263,
                    "roi": 0.181,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                }
            }
        },
    )

    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )
    shots = next(v for v in bundle.verdicts if v.market == "shots_on_goal")

    assert shots.supported is True
    assert "has not been replicated" in shots.reason


def test_a_conclusive_LOSS_is_never_reported_as_supported(tmp_path: Path) -> None:
    """The defect this file exists to prevent recurring.

    `supported` was set whenever the corrected interval excluded zero, with
    no reference to which side of zero it excluded. The NHL `points` market
    measures -4.4% over 6,202 bets with a corrected interval excluding zero,
    and was therefore labelled **supported** in the one document written to
    inform the decision about enabling it.

    Worse, it did not stop at the label. `recommendation()` lists
    `supported_markets` under the sentence "the evidence is consistent with
    enabling ...", so once the two outstanding evidence files existed the
    bundle would have recommended enabling a market demonstrated to lose
    money. It was masked only by those files being absent.

    A conclusive loss is the strongest argument AGAINST enabling a market.
    It must never be rendered as the argument for.
    """
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 6202,
                    "roi": -0.044,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                    "adjusted_low": -0.081,
                    "adjusted_high": -0.007,
                }
            }
        },
    )
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    verdict = next(v for v in bundle.verdicts if v.market == "points")
    assert verdict.supported is False, (
        "a market measured at -4.4% with an interval excluding zero was "
        "reported as supported"
    )
    assert "points" not in bundle.supported_markets
    assert "demonstrated deficit" in verdict.reason
    assert "consistent with enabling" not in bundle.recommendation()


def test_a_conclusive_WIN_is_still_reported_as_supported(tmp_path: Path) -> None:
    """The fix must not simply disable the branch.

    If requiring a positive sign also suppressed genuine positive results,
    the bundle would be uninformative in the one direction it exists to
    inform, and the test above would pass for the wrong reason.
    """
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "blocked_shots": {
                    "bets": 4293,
                    "roi": 0.049,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                    "adjusted_low": 0.008,
                    "adjusted_high": 0.090,
                }
            }
        },
    )
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    verdict = next(v for v in bundle.verdicts if v.market == "blocked_shots")
    assert verdict.supported is True
    assert "blocked_shots" in bundle.supported_markets
    assert "consistent with enabling" in bundle.recommendation()


def test_a_conclusive_interval_with_an_unreadable_return_is_not_supported(
    tmp_path: Path,
) -> None:
    """Unknown sign falls to the deficit branch, not the favourable one.

    A bundle that assumes the good reading when it cannot tell is a bundle
    that flatters by default, and every flattering default in this
    repository has eventually been wrong.
    """
    _all_evidence_present(tmp_path)
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "assists": {
                    "bets": 3761,
                    "roi": None,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                }
            }
        },
    )
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=tmp_path, repository_root=tmp_path
    )

    verdict = next(v for v in bundle.verdicts if v.market == "assists")
    assert verdict.supported is False
    assert "sign is unknown" in verdict.reason
