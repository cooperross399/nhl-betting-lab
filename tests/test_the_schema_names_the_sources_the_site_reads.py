"""web/SCHEMA.md named two sources the site builder never reads.

Its source-mapping paragraph said the Results page's finals come "from the
boxscore cache via `build_datasets.load_team_games`" and that
`record.forward` comes "from `forward_evidence.py` + `closing_lines.py`".
Neither is what `web/build_site_json.py` does:

* `settle()` takes every final from `schedule_for(day)`, a live GET of the
  NHL schedule endpoint (`api-web.nhle.com/v1/schedule/<date>`), keeping the
  games whose `gameState` is OFF or FINAL. `load_team_games` is called in one
  place, `load_model`, where it fits the team model, dates the published
  back-to-back chip (`rest.last_played_dates`) and decides the thin-history
  gate behind the schedule-only board; no final is ever read from it. The
  difference is not cosmetic: a reader debugging a wrong final would go
  looking in a cache the page never saw. And without the network the build
  does not "settle nothing": `fetch_json` does not catch the error and
  `build_board` calls `schedule_for` first, so the whole build fails and
  writes neither `board.json` nor `results.json`.
* `record.forward` is `load_record(data/outputs/forward_evidence.json)`, the
  file `forward_evidence.save_forward_report` writes: the forward ledger's
  SIZE (wagers, markets, date span, unsettleable), never its return. Nothing
  in the builder imports or reads `closing_lines`.
* `pick` is read from `data/outputs/gameday_card.json`, the file
  `reports/gameday_card.save_card` writes.

Found by the failure-shape audit (defect g25), confirmed on main d0cc593.

What these tests hold:

* the real `settle()`, over a frozen board, grades the scores the NHL
  schedule endpoint answered with, and does so with `load_team_games`
  poisoned — so the finals cannot be coming from the game history;
* the real `main()` with the network down raises and writes neither file,
  and SCHEMA.md says the build fails rather than settling nothing;
* the functions `settle()` reaches, transitively, that open a URL are
  derived from the builder's own syntax tree, not written down here;
  SCHEMA.md's finals sentence names every one of them that `settle()` calls
  itself, names the endpoint, and affirms neither `load_team_games` nor the
  boxscore cache as the source (a negated mention is allowed);
* the builder's syntax tree never mentions `closing_lines`; `build_board`'s
  one `load_record` call resolves, through constants and imports, to
  `forward_evidence.json`; the real `load_record` publishes the ledger's
  size; and SCHEMA.md's `record.forward` sentence names that file,
  `load_record` and `save_forward_report`, and not `closing_lines`;
* the real `save_card` writes the file `build_board` reads, and SCHEMA.md's
  `pick` sentence names that file and `save_card`.

The limit, stated rather than widened: the prose checks read the sentences of
the source-mapping paragraph that name finals, the network, `pick` and
`record.forward`. A false source stated somewhere else in SCHEMA.md is
invisible to them, and the negation reading is clause-level, not a parser.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import re
import urllib.error
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "web" / "build_site_json.py"
SCHEMA = PROJECT_ROOT / "web" / "SCHEMA.md"

DAY = date(2026, 10, 8)
GAME_ID = "2026020101"


def site_module() -> ModuleType:
    """`web/build_site_json.py`, loaded by path as the workflow runs it."""
    spec = importlib.util.spec_from_file_location("_site_build_sources", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def builder_tree() -> ast.Module:
    return ast.parse(BUILD_SCRIPT.read_text(encoding="utf-8"))


# -- the code's own answer ---------------------------------------------------


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _called_names(fn: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _reachable(tree: ast.Module, start: str) -> set[str]:
    """Module-level functions `start` calls, transitively."""
    functions = _functions(tree)
    seen: set[str] = set()
    stack = [start]
    while stack:
        for callee in _called_names(functions[stack.pop()]):
            if callee in functions and callee not in seen and callee != start:
                seen.add(callee)
                stack.append(callee)
    return seen


def _fetches(tree: ast.Module, name: str) -> bool:
    """Whether a module-level function opens a URL, directly or through one it calls."""
    functions = _functions(tree)
    return any(
        isinstance(node, ast.Attribute) and node.attr == "urlopen"
        for fn in {name, *_reachable(tree, name)}
        for node in ast.walk(functions[fn])
    )


def settle_fetchers() -> set[str]:
    """Every function `settle()` reaches, transitively, that opens a URL."""
    tree = builder_tree()
    return {name for name in _reachable(tree, "settle") if _fetches(tree, name)}


def settle_fetch_entries() -> set[str]:
    """Of those, the ones `settle()` names itself: the reader that says WHAT
    is read. `fetch_json` below them is how it is read."""
    tree = builder_tree()
    return settle_fetchers() & _called_names(_functions(tree)["settle"])


def _import_map(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    """Local name -> (module, attribute or None), for every import anywhere."""
    names: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names[alias.asname or alias.name.split(".")[0]] = (alias.name, None)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                names[alias.asname or alias.name] = (node.module, alias.name)
    return names


def _import_value(module: str, attr: str | None) -> object:
    mod = importlib.import_module(module)
    if attr is None:
        return mod
    try:
        return getattr(mod, attr)
    except AttributeError:
        return importlib.import_module(f"{module}.{attr}")


def resolved_strings(expr: ast.AST, tree: ast.Module) -> set[str]:
    """The string constants an expression is built from, following module-level
    assignments and imports, so `lab / "data" / REPORT` or
    `lab / fe.REPORT_JSON_FILENAME` resolves as well as a literal does."""
    assigns = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    imports = _import_map(tree)
    found: set[str] = set()
    for node in ast.walk(expr):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node, ast.Name) and node.id in assigns:
            found |= resolved_strings(assigns[node.id], tree)
        elif isinstance(node, ast.Name) and node.id in imports:
            value = _import_value(*imports[node.id])
            if isinstance(value, str):
                found.add(value)
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in imports
        ):
            value = getattr(_import_value(*imports[node.value.id]), node.attr, None)
            if isinstance(value, str):
                found.add(value)
    return found


# -- the doc's answer ---------------------------------------------------------


def source_mapping_sentences() -> list[str]:
    text = SCHEMA.read_text(encoding="utf-8")
    start = text.index("`web/build_site_json.py` is the reference writer.")
    paragraph = text[start:].split("\n\n", 1)[0]
    # Sentences end at ". " or at the paragraph's end; a "." inside a
    # backticked name (`build_datasets.load_team_games`) is not followed by
    # a space, so it does not split.
    return [s.strip() for s in re.split(r"(?<=\.)\s+", paragraph) if s.strip()]


def sentences_about(pattern: str) -> list[str]:
    found = [s for s in source_mapping_sentences() if re.search(pattern, s)]
    assert found, f"SCHEMA.md's source mapping has no sentence matching {pattern!r}"
    return found


def affirmed(sentence: str) -> str:
    """The sentence with its negated clauses removed.

    "never from `build_datasets.load_team_games`" is a correct statement and
    must not read as naming that source. A clause runs from "never", "not" or
    "no" to the next comma, semicolon, colon or sentence end; dots inside
    backticked names are masked first so they do not end it.
    """
    masked = re.sub(r"`[^`]*`", lambda m: m.group(0).replace(".", "·"), sentence)
    stripped = re.sub(r"\b(?:never|not|no)\b[^,;:.]*", " ", masked, flags=re.IGNORECASE)
    return stripped.replace("·", ".")


def test_the_negation_reading_keeps_an_affirmation_and_drops_a_denial() -> None:
    # Guards the helper both ways, so the prose check below can neither
    # reject a correct denial nor wave through a false claim.
    assert "load_team_games" in affirmed("Finals come from `build_datasets.load_team_games`.")
    assert "load_team_games" not in affirmed("Finals come from `schedule_for`, never from `build_datasets.load_team_games`.")
    assert "boxscore" not in affirmed("Finals are not read from the boxscore cache; `schedule_for` reads them.")


# -- finals ------------------------------------------------------------------


def _frozen_board(history: Path) -> None:
    history.mkdir(parents=True)
    board = {
        "phase": "regular",
        "games": [{
            "id": GAME_ID, "startUtc": f"{DAY.isoformat()}T23:00:00Z", "priced": False, "pick": None,
            "away": {"abbr": "MTL", "projGoals": 2.9}, "home": {"abbr": "TOR", "projGoals": 3.1},
        }],
    }
    (history / f"{DAY.isoformat()}.json").write_text(json.dumps(board), encoding="utf-8")


def test_settle_reads_its_finals_from_the_nhl_schedule_endpoint_not_the_game_history(
    tmp_path: Path, monkeypatch
) -> None:
    module = site_module()
    history = tmp_path / "history"
    _frozen_board(history)

    # The game history, poisoned: any read of it for a final fails the test.
    import nhl_betting_lab.data.build_datasets as build_datasets

    def poisoned(*_a, **_k):
        raise AssertionError("settle() read a final from build_datasets.load_team_games")

    monkeypatch.setattr(build_datasets, "load_team_games", poisoned)

    asked: list[str] = []

    def endpoint(url: str) -> dict:
        asked.append(url)
        return {"gameWeek": [{"date": DAY.isoformat(), "games": [{
            "id": int(GAME_ID), "gameState": "OFF", "gameOutcome": {"lastPeriodType": "OT"},
            "awayTeam": {"abbrev": "MTL", "score": 4}, "homeTeam": {"abbrev": "TOR", "score": 3},
        }]}]}

    monkeypatch.setattr(module, "fetch_json", endpoint)

    results = module.settle(DAY, history)

    assert asked == [f"{module.NHL}/schedule/{DAY.isoformat()}"], asked
    assert module.NHL == "https://api-web.nhle.com/v1"
    [game] = results["games"]
    assert (game["away"]["final"], game["home"]["final"], game["finish"]) == (4, 3, "OT"), game


def test_without_the_network_the_build_fails_and_writes_neither_file(tmp_path: Path, monkeypatch) -> None:
    module = site_module()

    def offline(url: str) -> dict:
        raise urllib.error.URLError("network unreachable")

    monkeypatch.setattr(module, "fetch_json", offline)
    out = tmp_path / "out"
    with pytest.raises(urllib.error.URLError):
        module.main(["--lab", str(tmp_path / "lab"), "--out", str(out), "--date", DAY.isoformat()])
    assert not (out / "board.json").exists()
    assert not (out / "results.json").exists()


def test_the_derivation_finds_the_schedule_read() -> None:
    # Guards the derivation itself: if it found nothing, the doc check below
    # would pass on an empty set.
    assert "schedule_for" in settle_fetchers()
    assert settle_fetch_entries(), "settle() calls no function that opens a URL?"
    assert "load_team_games" not in _reachable(builder_tree(), "settle")


def test_schema_names_the_finals_source_settle_actually_calls() -> None:
    finals = sentences_about(r"\bfinals?\b")
    joined = " ".join(finals)
    for name in sorted(settle_fetch_entries()):
        assert f"`{name}`" in joined, (
            f"settle() takes its finals through `{name}`, and SCHEMA.md's finals sentence does not name it: {finals}"
        )
    endpoint = site_module().NHL.split("://", 1)[1] + "/schedule"
    assert endpoint in joined, f"SCHEMA.md's finals sentence does not name the endpoint {endpoint}: {finals}"
    for sentence in finals:
        claimed = affirmed(sentence)
        assert "load_team_games" not in claimed, (
            "SCHEMA.md says finals come through load_team_games; settle() never calls it: " + sentence
        )
        assert "boxscore" not in claimed.lower(), (
            "SCHEMA.md says finals come from the boxscore cache; settle() reads the NHL schedule: " + sentence
        )
        assert "settles nothing" not in sentence, (
            "without the network the build raises and writes nothing; it does not settle nothing: " + sentence
        )


def test_schema_says_the_build_fails_without_the_network() -> None:
    offline = sentences_about(r"(?i)without the network")
    joined = " ".join(offline)
    assert "fails" in joined, offline
    assert "`board.json`" in joined and "`results.json`" in joined, offline


def test_schema_does_not_confine_the_game_history_to_fitting_the_model() -> None:
    history = sentences_about(r"load_team_games")
    joined = " ".join(history)
    # load_model feeds the same table to the fit, to last_played_dates (the
    # published b2b chip) and to the THIN_HISTORY_GAMES gate.
    tree = builder_tree()
    load_model = _functions(tree)["load_model"]
    uses = {node.id for node in ast.walk(load_model) if isinstance(node, ast.Name)}
    assert {"last_played_dates", "THIN_HISTORY_GAMES"} <= uses
    assert "only to fit" not in joined, history
    assert "last_played_dates" in joined and "thin-history" in joined, history
    assert re.search(r"never[^.]*settle", joined), history


# -- record.forward ----------------------------------------------------------


def test_the_builder_never_reads_closing_lines() -> None:
    tree = builder_tree()
    names = {
        getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "module", None)
        for node in ast.walk(tree)
    }
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not any(n and "closing_lines" in n for n in names)
    # And the board's record is load_record over forward_evidence.json,
    # however the path is spelled.
    build_board = _functions(tree)["build_board"]
    calls = [
        node for node in ast.walk(build_board)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "load_record"
    ]
    assert len(calls) == 1
    assert "forward_evidence.json" in resolved_strings(calls[0].args[0], tree)


def test_the_path_resolver_follows_constants_and_imports() -> None:
    tree = ast.parse(
        "from nhl_betting_lab import forward_evidence as fe\n"
        "from nhl_betting_lab.forward_evidence import REPORT_JSON_FILENAME\n"
        "LOCAL = 'forward_evidence.json'\n"
    )
    for spelling in ("lab / fe.REPORT_JSON_FILENAME", "lab / REPORT_JSON_FILENAME", "lab / LOCAL"):
        assert "forward_evidence.json" in resolved_strings(ast.parse(spelling, mode="eval").body, tree), spelling
    assert "forward_evidence.json" not in resolved_strings(ast.parse("lab / 'other.json'", mode="eval").body, tree)


def test_record_forward_is_the_ledger_size_read_from_forward_evidence_json(tmp_path: Path) -> None:
    module = site_module()
    report = tmp_path / "forward_evidence.json"
    report.write_text(json.dumps({
        "rows": 30, "wagers": 9, "unsettleable": 1,
        "markets": {"moneyline": {"first_date": "2026-10-01", "last_date": "2026-10-05", "roi": 0.4}},
    }), encoding="utf-8")
    forward = module.load_record(report)["forward"]
    assert (forward["wagers"], forward["markets"], forward["firstDate"], forward["lastDate"]) == (
        9, 1, "2026-10-01", "2026-10-05",
    )
    assert "roi" not in json.dumps(forward)


def test_schema_names_the_record_forward_source_the_builder_actually_reads() -> None:
    from nhl_betting_lab import forward_evidence

    forward = sentences_about(r"record\.forward")
    joined = " ".join(forward)
    assert forward_evidence.REPORT_JSON_FILENAME in joined, forward
    assert "`load_record`" in joined, forward
    # The writer, named as the pick clause names save_card.
    assert "save_forward_report" in joined, forward
    for sentence in forward:
        assert "closing_lines" not in sentence, (
            "SCHEMA.md says record.forward comes from closing_lines; the builder never reads it: " + sentence
        )


# -- pick --------------------------------------------------------------------


def test_the_card_file_save_card_writes_is_the_one_the_board_reads(tmp_path: Path) -> None:
    from nhl_betting_lab.reports.gameday_card import GamedayCard, save_card

    written = Path(save_card(GamedayCard(generated_at="2026-10-08T12:00:00Z"), output_dir=tmp_path)["json"])
    assert written.is_file()
    tree = builder_tree()
    assert written.name in resolved_strings(_functions(tree)["build_board"], tree)


def test_schema_names_the_pick_source_the_builder_actually_reads() -> None:
    from nhl_betting_lab.reports.gameday_card import CARD_JSON_FILENAME

    pick = sentences_about(r"`pick` is")
    joined = " ".join(pick)
    assert CARD_JSON_FILENAME in joined, pick
    assert "save_card" in joined, pick
