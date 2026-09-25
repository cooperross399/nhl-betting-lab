"""The docs said the gameday cap covers a full slate and the card cannot read staging.

Neither is true, and both are the kind of sentence a reader acts on.

Found by the failure-shape audit (group docs-state-the-cap-and-staging-
truthfully, confirmed by two of three refuters), on the caps fixer's
read-only measurement (#159) against the real 2026-27 club schedules:

* **The per-event cap.** The provider bills every asked market once per
  region, and the lab has asked two (`odds_api.DEFAULT_REGIONS`, `us,us2`)
  since 2026-08-28, the day the cap was set. The 19 per-event markets Gameday
  Refresh asks therefore cost 19 x 2 = 38 credits an event under the
  pessimistic bound the cap is enforced against, and its cap of 320 buys 8
  events. CLAUDE.md said it "clips zero of the 185 nights (16 games x 19 =
  304)" and the workflow said "320 covers a sixteen-game slate at nineteen
  asked markets" — one region's arithmetic. On the real schedule it clips 72
  of the 185 nights and leaves 254 games unpriced, and on those nights every
  market only the per-event fetch prices (the seven props, the regulation
  three-way, team totals) is INCOMPLETE and excluded. 608 is the smallest cap
  that clips none; 640 clips none. Raising it spends credits and is Cooper's
  decision, pending — no cap changes here. The same omission said Provider
  Market Discovery's 380 buys twenty events (it buys 10), that
  `run_provider_shadow.py`'s 190 buys ten (5), and the Historical Props
  Purchase comment priced a bulk team slate at thirty credits (60).
* **Staging.** The `odds_api` docstring said "The card cannot read
  `data/staging/`", `write_provenance` wrote "Staging is invisible to the
  card" into every provenance file, and the shadow report told its reader
  "The card cannot read those files". `run_gameday_card.py` reads
  `data/staging/` directly — Gameday Refresh fetches into it and cards from it
  in one job. What stands between a staged price and a stake is the policy's
  allowlist, completeness and freshness, not invisibility.
* **The card's checks.** `docs/provider_allowlist_approval.md` said an
  allowlisted market still passes "staging validation, completeness,
  freshness, checksum, and the puck-drop guard" on every run. The card
  verifies no receipt and no checksum — the Provider Policy PR Gate does, on
  a pull request that touches the policy or a receipt and on every push to
  `main` — and it validates no staged file: one it cannot parse is skipped
  and its markets read as unavailable. The evidence bundle's note named
  "Staging validation" too.

What these tests hold, each on a real code path:

* the real card `main()`, over prices the shadow writer staged, prices them
  and stakes one — and the provenance file written beside them and the
  shadow report both say the card reads staging through those three gates;
* the real card cards from a policy citing a receipt that exists nowhere and
  from a staging directory holding a file it cannot parse — and neither the
  approval doc nor the evidence bundle lists a checksum or a staging
  validation among the card's checks;
* every "<cap> buys <n> events" statement in the operating docs, the
  workflows and the shadow script's `--help` equals what the real
  `fetch_player_props` buys at that cap and the default regions, and the
  caps the workflows actually run are stated that way.

The limit, stated rather than widened: the prose checks read the shapes
named here and the specific sentences that were false. A new false sentence
phrased some other way is invisible to them.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
import yaml

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import historical_team_prices as team
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports import allowlist_evidence, provider_shadow
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.staging_provider_policy import load_policy


ENVIRONMENT = {"NHL_ODDS_API_KEY": "k" * 24}

#: What Gameday Refresh and the discovery probe ask of every event.
PER_EVENT = list(odds_api.PER_EVENT_PROVIDER_MARKETS) + list(
    odds_api.ALTERNATE_PROVIDER_MARKETS
)

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

#: Every document that states what a per-event cap buys.
CAP_STATEMENTS = (
    "CLAUDE.md",
    "README.md",
    "docs/periphery_markets_decision.md",
    ".github/workflows/gameday-refresh.yml",
    ".github/workflows/provider-market-discovery.yml",
)

NUMBER_WORDS = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
        "twenty".split()
    )
}

#: "<cap> buys <n> events", the one shape these docs state a cap in.
BUYS = re.compile(
    r"\b(\d[\d,]*) buys (\d+|" + "|".join(NUMBER_WORDS) + r") events?\b",
    re.IGNORECASE,
)


def _prose(text: str) -> str:
    """One line of plain words: comment markers, markdown emphasis and line
    wrapping removed, so a sentence wrapped across a YAML comment reads as
    one sentence."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line[1:].strip() if line.startswith("#") else line for line in lines]
    return " ".join(" ".join(lines).replace("**", "").replace("`", "").split())


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def _load(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- what a cap buys, measured on the real fetch ------------------------


def _events_bought(cap: int) -> int:
    """How many events the real per-event fetch asks about at `cap`, at the
    regions production runs, on a board larger than any cap here affords.
    The requester answers from memory; nothing reaches the network."""
    listing = [
        {"id": f"evt{index:02d}", "commence_time": f"2026-10-13T{index % 24:02d}:00:00Z"}
        for index in range(40)
    ]
    requester = RecordingRequester(
        {
            "/events/": FakeResponse({"id": "x", "bookmakers": []}),
            "/events": FakeResponse(listing),
        }
    )
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT, requester=requester)
    provider.fetch_player_props(markets=PER_EVENT, credit_cap=cap)
    return sum(1 for url in requester.urls if "/events/" in url)


def _per_event_bound() -> int:
    """The provider's own pessimistic charge for one event of PER_EVENT."""
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT)
    return provider.estimate_prop_credits(events=1, markets=PER_EVENT)


def _count(word: str) -> int:
    return int(word) if word.isdigit() else NUMBER_WORDS[word.lower()]


def _workflow(name: str) -> dict:
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True.
    return document.get("on", document.get(True))


def _gameday_cap() -> int:
    """The cap Gameday Refresh runs: the dispatch default and the fallback a
    scheduled run (which has no inputs) uses. They must be one number."""
    default = int(
        _workflow("gameday-refresh.yml")["workflow_dispatch"]["inputs"][
            "props_credit_cap"
        ]["default"]
    )
    fallbacks = {
        int(value)
        for value in re.findall(
            r"inputs\.props_credit_cap \|\| '(\d+)'",
            (WORKFLOWS / "gameday-refresh.yml").read_text(encoding="utf-8"),
        )
    }
    assert fallbacks == {default}, (default, fallbacks)
    return default


def _discovery_cap() -> int:
    return int(
        _workflow("provider-market-discovery.yml")["workflow_dispatch"]["inputs"][
            "credit_cap"
        ]["default"]
    )


def test_production_asks_the_default_regions() -> None:
    """Every figure below is taken at `odds_api.DEFAULT_REGIONS`, which is
    right only while no workflow overrides it."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        assert "NHL_ODDS_REGIONS" not in path.read_text(encoding="utf-8"), path.name
    assert odds_api.count_regions(odds_api.DEFAULT_REGIONS) == 2
    assert _per_event_bound() == len(PER_EVENT) * 2 == 38


@pytest.mark.parametrize("relative", CAP_STATEMENTS)
def test_every_stated_cap_buys_what_the_fetch_buys(relative: str) -> None:
    prose = _prose(_read(relative))

    for cap, stated in BUYS.findall(prose):
        cap_value = int(cap.replace(",", ""))
        assert _count(stated) == _events_bought(cap_value), (
            f"{relative} says {cap} buys {stated} events; the fetch buys "
            f"{_events_bought(cap_value)} at {_per_event_bound()} credits an event"
        )


def test_the_gameday_cap_is_stated_at_what_it_buys() -> None:
    cap = _gameday_cap()
    bought = _events_bought(cap)
    claim = f"{cap} buys {bought} events"
    rate = f"{len(PER_EVENT)} markets x 2 regions = {_per_event_bound()} credits an event"

    assert bought == 8
    for relative in ("CLAUDE.md", ".github/workflows/gameday-refresh.yml"):
        prose = _prose(_read(relative))
        assert claim in prose, f"{relative} does not say {claim!r}"
        assert rate in prose, f"{relative} does not say {rate!r}"
    claude = _prose(_read("CLAUDE.md"))
    assert "clips zero of the 185 nights" not in claude
    assert "Cooper's decision, still pending" in claude
    gameday = _prose(_read(".github/workflows/gameday-refresh.yml"))
    assert "320 covers a sixteen-game slate" not in gameday
    assert "duplicate is 26,091 credits" not in gameday
    assert "on a twelve-game night across six markets is 72 credits" not in gameday


def test_the_probe_cap_is_stated_at_what_it_buys() -> None:
    cap = _discovery_cap()
    claim = f"{cap} buys {_events_bought(cap)} events"

    discovery = _prose(_read(".github/workflows/provider-market-discovery.yml"))
    assert claim in discovery, claim
    assert "The cap buys twenty events" not in discovery
    periphery = _prose(_read("docs/periphery_markets_decision.md"))
    assert f"{_gameday_cap()} buys {_events_bought(_gameday_cap())} events" in periphery
    assert claim in periphery
    assert "the gameday cap is 320 (sixteen games, the largest possible slate)" not in periphery


def test_the_shadow_scripts_help_states_what_its_cap_buys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `--help` is generated, so it is read as the script prints it."""
    module = _load("run_provider_shadow.py")

    with pytest.raises(SystemExit) as exit_info:
        module.main(["--help"])
    assert exit_info.value.code == 0
    printed = _prose(capsys.readouterr().out)

    statements = BUYS.findall(printed)
    assert statements, "the help no longer says what its default cap buys"
    for cap, stated in statements:
        assert _count(stated) == _events_bought(int(cap)), (cap, stated)
    assert f"the default 190 buys {_events_bought(190)} events" in printed
    assert "One credit per market per event." not in printed
    assert "which is ten events at this default" not in printed
    # The README's copy of the same command says the same thing.
    readme = _prose(_read("README.md"))
    assert f"190 buys {_events_bought(190)} events" in readme
    assert "props are one credit per market per event and the cap is hard" not in readme


def test_the_bulk_team_slate_is_stated_at_its_bill() -> None:
    bill = team.estimate_credits(
        snapshots=1,
        markets=len(team.BULK_MARKETS),
        regions=odds_api.count_regions(odds_api.DEFAULT_REGIONS),
    )

    purchase = _prose(_read(".github/workflows/historical-props-purchase.yml"))
    assert bill == 60
    assert f"a whole slate costs {bill} credits" in purchase
    assert "thirty credits" not in purchase


# -- what the card reads, run through the real card ----------------------


#: Wednesday noon in New York; the game is that evening.
CARD_AT = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)
GAME_AT = "2026-10-07T23:00:00Z"
SNAPSHOT_DAY = "2026-10-07"
STAGED_AT = (CARD_AT - timedelta(hours=1)).isoformat(timespec="seconds")


def _event() -> dict:
    """Toronto at home to Boston, one book, a moneyline."""
    return {
        "id": "evt-tor-bos",
        "commence_time": GAME_AT,
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


def _shadow_stage(staging: Path) -> dict:
    """Stage one slate the way `run_provider_shadow.py --live` does: the
    production writer, then the production provenance beside it."""
    written = odds_api.write_staging(
        odds_api.normalize_event(_event(), fetched_at=STAGED_AT),
        filename=odds_api.STAGING_PRICES_FILENAME,
        staging_dir=staging,
        overwrite=True,
    )
    provenance = odds_api.write_provenance(
        odds_api.FetchResult(fetched_at=STAGED_AT, events_seen=1, events_priced=1),
        configuration=odds_api.OddsApiProvider(
            environment=ENVIRONMENT
        ).public_configuration(),
        staging_files=[written],
        staging_dir=staging,
    )
    return json.loads(provenance.read_text(encoding="utf-8"))


class _StubModel:
    report = SimpleNamespace(summary_line=lambda: "stub model")
    ambiguous_names: list = []

    def fit(self, _frame):
        return self


def _price_what_it_is_given(prices, _model, **_kwargs):
    """Toronto 62%, Boston 38% on every moneyline row the card hands over:
    at +150 Toronto is a best bet."""
    opinions = {}
    for row in prices.itertuples():
        if str(row.market) != "moneyline":
            continue
        selection = str(row.selection)
        opinions[
            selection_key(row, market="moneyline", selection=selection, line=None)
        ] = 0.62 if selection == "home" else 0.38
    return opinions, []


@pytest.fixture
def card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real card `main()` over scratch directories, the models stubbed,
    every default directory pointed away from the real tree, and a policy
    whose receipt id names a receipt that exists nowhere."""
    raw = tmp_path / "default_raw"
    (raw / "nhl" / "boxscore").mkdir(parents=True)
    payload = boxscore_payload(game_id=1, game_state="OFF")
    payload["homeTeam"].update(
        abbrev="TOR", placeName={"default": "Toronto"},
        commonName={"default": "Maple Leafs"},
    )
    payload["awayTeam"].update(
        abbrev="BOS", placeName={"default": "Boston"},
        commonName={"default": "Bruins"},
    )
    (raw / "nhl" / "boxscore" / "1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    default_processed = tmp_path / "default_processed"
    default_processed.mkdir()
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", default_processed)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "no_schedule")

    policy_path = tmp_path / "policy" / "staging_provider_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
                "provider_allowlist_entries": {
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-09-24",
                        "reviewer_name": "A Reviewer",
                        "evidence_receipt_id": "a-receipt-that-exists-nowhere",
                        "required_markets": ["moneyline"],
                        "max_provider_run_age_hours": 12,
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )

    module = _load("run_gameday_card.py")
    monkeypatch.setattr(module, "load_player_logs",
                        lambda _dir: pd.DataFrame({"player_id": [1]}))
    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "PlayerPropsModel", _StubModel)
    monkeypatch.setattr(module, "TeamModel", _StubModel)
    monkeypatch.setattr(module, "current_rosters", lambda **_: {})
    monkeypatch.setattr(module, "price_props", lambda *a, **k: ({}, []))
    monkeypatch.setattr(module, "price_team_markets", _price_what_it_is_given)
    monkeypatch.setattr(
        module, "load_policy",
        lambda: load_policy(policy_path, repository_root=tmp_path),
    )

    staging = tmp_path / "staging"
    outputs = tmp_path / "outputs"

    def run() -> SimpleNamespace:
        code = module.main(
            [
                "--staging-dir", str(staging),
                "--processed-dir", str(tmp_path / "processed"),
                "--output-dir", str(outputs),
                "--now", CARD_AT.isoformat(),
            ]
        )
        card_json = json.loads(
            (outputs / "gameday_card.json").read_text(encoding="utf-8")
        )
        snapshot = fe.snapshots_dir(outputs / "archive") / f"{SNAPSHOT_DAY}.csv"
        return SimpleNamespace(code=code, card=card_json, snapshot=snapshot)

    return SimpleNamespace(run=run, staging=staging, root=tmp_path)


def _staked(card_json: dict) -> float:
    return sum(float(row.get("suggested_units") or 0) for row in card_json["best_bets"])


#: The three gates every statement about staging must name.
GATES = ("allowlist", "every game in the slate", "max_provider_run_age_hours")


def test_the_card_stakes_what_a_shadow_run_staged_and_the_provenance_says_so(
    card,
) -> None:
    provenance = _shadow_stage(card.staging)

    result = card.run()

    assert result.code == 0
    assert result.card["card_generated"] is True, result.card["blockers"]
    staked = [row for row in result.card["best_bets"] if row.get("suggested_units")]
    assert staked and staked[0]["book"] == "DraftKings"
    assert float(staked[0]["american_odds"]) == 150.0, "not the staged price"
    assert result.snapshot.exists(), "the staged price was frozen as an opinion"

    note = provenance["note"]
    assert "invisible" not in note, note
    assert "The gameday card reads these staged prices" in note, note
    for gate in GATES:
        assert gate in note, (gate, note)
    assert "reviewed human approval" in note


def test_the_shadow_report_says_the_card_reads_staging_through_its_gates(
    tmp_path: Path,
) -> None:
    prices = pd.DataFrame(
        odds_api.normalize_event(_event(), fetched_at=STAGED_AT)
    )
    summary, eligibility, discovery = provider_shadow.build_shadow_summary(
        prices,
        policy=load_policy(repository_root=tmp_path),
        provider_name=odds_api.PROVIDER_NAME,
        now=CARD_AT,
    )

    rendered = _prose(provider_shadow.render_shadow(summary, eligibility, discovery))

    assert "cannot read" not in rendered
    assert "The gameday card reads data/staging/" in rendered
    for gate in GATES:
        assert gate in rendered, gate


def test_the_card_checks_no_receipt_and_no_checksum(card) -> None:
    """The fixture's policy cites a receipt id that names no file anywhere,
    and the card cards and stakes regardless: nothing on its path reads a
    receipt or recomputes an evidence checksum. The Provider Policy PR Gate
    does, and the docs must say it is the gate's and not the card's."""
    _shadow_stage(card.staging)
    assert not any(card.root.rglob("a-receipt-that-exists-nowhere*"))

    result = card.run()

    assert result.card["card_generated"] is True, result.card["blockers"]
    assert _staked(result.card) > 0

    approval = _prose(_read("docs/provider_allowlist_approval.md"))
    assert (
        "staging validation, completeness, freshness, checksum, and the "
        "puck-drop guard" not in approval
    )
    assert (
        "Evidence checksums are recomputed by the Provider Policy PR Gate"
        in approval
    )
    bundle = allowlist_evidence.build_bundle(
        provider_name=odds_api.PROVIDER_NAME,
        output_dir=card.root / "bundle_outputs",
        repository_root=card.root,
        now=CARD_AT,
    )
    notes = " ".join(bundle.notes)
    assert "Staging validation" not in notes, notes
    assert "The PR gate recomputes them" in notes


def test_a_staged_file_the_card_cannot_parse_is_skipped_not_refused(card) -> None:
    """No validation gate stands on staging: an unparseable per-event file is
    skipped, its markets read as unavailable, and the team file beside it
    still cards. The approval doc must say so rather than promise a check."""
    _shadow_stage(card.staging)
    (card.staging / odds_api.STAGING_PROPS_FILENAME).write_text("", encoding="utf-8")

    result = card.run()

    assert result.card["card_generated"] is True, result.card["blockers"]
    assert _staked(result.card) > 0
    approval = _prose(_read("docs/provider_allowlist_approval.md"))
    assert "a staged file the card cannot parse is skipped" in approval


@pytest.mark.parametrize(
    "source",
    [
        "odds_api",
        "provider_shadow",
        "run_provider_shadow.py",
        "docs/provider_allowlist_approval.md",
        "docs/project_status_for_claude.md",
    ],
)
def test_no_statement_says_the_card_cannot_read_staging(source: str) -> None:
    """The sentences that were false, by their own words — a list, not a
    detector. The card tests above are the evidence; these are the places
    that denied it, and each must now say the card reads staging."""
    if source == "odds_api":
        text = odds_api.__doc__ or ""
    elif source == "provider_shadow":
        text = provider_shadow.__doc__ or ""
    elif source.endswith(".py"):
        text = _load(source).__doc__ or ""
    else:
        text = _read(source)
    prose = _prose(text)

    for sentence in (
        "The card cannot read data/staging/",
        "the card cannot read the files it writes",
        "which the card cannot read",
        "The card cannot read what it writes",
    ):
        assert sentence not in prose, (source, sentence)
    assert "card reads" in prose, f"{source} no longer says what the card reads"
