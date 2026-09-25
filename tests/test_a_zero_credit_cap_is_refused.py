"""A credit cap of 0 switched the per-event cap off, and two live entry points took it.

`OddsApiProvider.fetch_player_props` guarded each request with
`if credit_cap and result.credits_spent + per_event > credit_cap`, so a cap of
0 — also the parameter's default — skipped the check entirely and fetched
every event on the board. A negative cap skipped every event instead, so
exactly 0, the natural spelling of "spend nothing", was the one value that
spent the most. `run_provider_shadow.py --live --props` and
`capture_closing_lines.py --live` passed a dispatched "0" straight through
(both workflows' `${{ inputs.X || 'default' }}` keeps a typed "0"), while
`capture_line_movement.py`, `discover_nhl_markets.py` and the `buy_*`
scripts all refuse a cap of 0 or less.

Found by the failure-shape audit (2 of 3 refuters). Measured with a fake
requester, 19 per-event markets at two regions (38 credits an event): on a
30-event board a cap of 190 made 5 per-event requests, counted 190 credits
and warned that the rest were skipped; a cap of 0 made 30 requests, counted
1,140, and warned about nothing.

What these tests hold:

* the library refuses a zero, negative or missing cap before it asks the
  provider anything, and a positive cap still buys what it affords and says
  what it skipped;
* both scripts refuse a zero or negative cap at parse time under `--live`
  (the shadow script with `--props`, the only path that reads the cap),
  before a provider is built or a credential is loaded;
* the shadow script without `--props` never reads the cap, so it is not
  refused for one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api


ENVIRONMENT = {"NHL_ODDS_API_KEY": "k" * 24}

PER_EVENT = list(odds_api.PER_EVENT_PROVIDER_MARKETS) + list(
    odds_api.ALTERNATE_PROVIDER_MARKETS
)


def _board(events: int) -> RecordingRequester:
    listing = [
        {"id": f"evt{index}", "commence_time": f"2026-10-09T{index % 24:02d}:00:00Z"}
        for index in range(events)
    ]
    return RecordingRequester(
        {
            "/events/": FakeResponse({"id": "x", "bookmakers": []}),
            "/events": FakeResponse(listing),
        }
    )


def _per_event_requests(requester: RecordingRequester) -> int:
    return sum(1 for url in requester.urls if "/events/" in url)


# -- the library -------------------------------------------------------


@pytest.mark.parametrize("cap", [0, -5, None], ids=["zero", "negative", "missing"])
def test_the_library_refuses_a_cap_that_is_not_positive_before_asking(
    cap: int | None,
) -> None:
    requester = _board(30)
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester, regions="us,us2"
    )
    kwargs = {} if cap is None else {"credit_cap": cap}

    with pytest.raises(odds_api.ProviderError, match="positive credit cap"):
        provider.fetch_player_props(markets=PER_EVENT, **kwargs)

    assert requester.calls == [], "asked the provider before refusing"


def test_a_positive_cap_buys_what_it_affords_and_says_what_it_skipped() -> None:
    """The finding's own board: 30 events at 38 credits, cap 190."""
    requester = _board(30)
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester, regions="us,us2"
    )

    result = provider.fetch_player_props(markets=PER_EVENT, credit_cap=190)

    assert _per_event_requests(requester) == 5
    assert result.credits_spent == 190
    assert any("25 event(s) were not fetched" in note for note in result.warnings)


# -- the scripts -------------------------------------------------------


def _load(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _forbid_provider(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list:
    """Record any attempt to load a credential or build a provider, and fail
    the build loudly, so an unguarded script can never reach the network."""
    touched: list[str] = []

    def no_env(*_args, **_kwargs):
        touched.append("load_provider_env")
        raise AssertionError("loaded the credential before refusing the cap")

    def no_provider(*_args, **_kwargs):
        touched.append("OddsApiProvider")
        raise AssertionError("built a provider before refusing the cap")

    monkeypatch.setattr(module, "load_provider_env", no_env)
    monkeypatch.setattr(module.odds_api, "OddsApiProvider", no_provider)
    return touched


@pytest.mark.parametrize("cap", ["0", "-1"])
def test_the_shadow_script_refuses_the_cap_before_building_a_provider(
    cap: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load("run_provider_shadow.py")
    touched = _forbid_provider(module, monkeypatch)

    with pytest.raises(SystemExit) as exit_info:
        module.main(
            [
                "--live", "--props", "--credit-cap", cap,
                "--staging-dir", str(tmp_path / "staging"),
                "--output-dir", str(tmp_path / "outputs"),
            ]
        )

    assert exit_info.value.code == 2
    assert touched == []
    assert "positive --credit-cap" in capsys.readouterr().err
    assert not (tmp_path / "staging").exists()


def test_the_shadow_script_without_props_does_not_read_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Provider Market Discovery passes a cap with `--props` off; the cap
    governs nothing there, so it is no reason to refuse the run."""
    module = _load("run_provider_shadow.py")
    asked: list[str] = []

    class TeamOnly:
        def fetch_team_markets(self, **_kwargs):
            asked.append("team")
            return odds_api.FetchResult(fetched_at="2026-10-09T12:00:00+00:00")

        def fetch_player_props(self, **_kwargs):
            asked.append("per-event")
            raise AssertionError("the per-event fetch was not asked for")

        def public_configuration(self) -> dict:
            return {}

    monkeypatch.setattr(module, "load_provider_env", lambda: _Loaded())
    monkeypatch.setattr(module.odds_api, "OddsApiProvider", lambda: TeamOnly())

    code = module.main(
        [
            "--live", "--credit-cap", "0",
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(tmp_path / "outputs"),
        ]
    )
    capsys.readouterr()

    assert code == 0
    assert asked == ["team"]


class _Loaded:
    warnings: list = []

    @staticmethod
    def summary_line() -> str:
        return "credential: stubbed for the test"


@pytest.mark.parametrize("cap", ["0", "-1"])
def test_the_closing_capture_refuses_the_cap_before_building_a_provider(
    cap: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load("capture_closing_lines.py")
    touched = _forbid_provider(module, monkeypatch)

    with pytest.raises(SystemExit) as exit_info:
        module.main(
            ["--live", "--credit-cap", cap,
             "--processed-dir", str(tmp_path / "processed")]
        )

    assert exit_info.value.code == 2
    assert touched == []
    assert "positive --credit-cap" in capsys.readouterr().err
    assert not (tmp_path / "processed").exists()
