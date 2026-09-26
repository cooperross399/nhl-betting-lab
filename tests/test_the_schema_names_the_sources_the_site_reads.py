"""web/SCHEMA.md named two sources the site builder never reads.

Its source-mapping paragraph said the Results page's finals come "from the
boxscore cache via `build_datasets.load_team_games`" and that
`record.forward` comes "from `forward_evidence.py` + `closing_lines.py`".
Neither is what `web/build_site_json.py` does:

* `settle()` takes every final from `schedule_for(day)`, a live GET of the
  NHL schedule endpoint (`api-web.nhle.com/v1/schedule/<date>`), keeping the
  games whose `gameState` is OFF or FINAL. `load_team_games` is called in one
  place, `load_model`, to fit the team model the board projects from; no
  final is ever read from it. The difference is not cosmetic: a reader
  debugging a wrong final would go looking in a cache the page never saw,
  and a Results page built with no network settles nothing, whatever the
  cache holds.
* `record.forward` is `load_record(data/outputs/forward_evidence.json)`: the
  forward ledger's SIZE (wagers, markets, date span, unsettleable), never its
  return. Nothing in the builder imports or reads `closing_lines`.

Found by the failure-shape audit (defect g25), confirmed on main d0cc593.

What these tests hold:

* the real `settle()`, over a frozen board, grades the scores the NHL
  schedule endpoint answered with, and does so with `load_team_games`
  poisoned — so the finals cannot be coming from the game history;
* the functions `settle()` reaches that fetch over the network are derived
  from the builder's own syntax tree, not written down here, and SCHEMA.md's
  finals sentence names every one of them, names the endpoint, and does not
  name `load_team_games` or the boxscore cache;
* the builder's syntax tree never mentions `closing_lines`, the real
  `load_record` publishes the ledger's size from `forward_evidence.json`,
  and SCHEMA.md's `record.forward` sentence names that file and function and
  not `closing_lines`.

The limit, stated rather than widened: the prose checks read the sentences of
the source-mapping paragraph that name finals and `record.forward`. A false
source stated somewhere else in SCHEMA.md is invisible to them.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from types import ModuleType

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


# -- the code's own answer ---------------------------------------------------


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _called_names(fn: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _reachable(tree: ast.Module, start: str) -> list[str]:
    """Module-level functions `start` calls, transitively, in call order."""
    functions = _functions(tree)
    seen: list[str] = []
    stack = [start]
    while stack:
        name = stack.pop()
        for callee in sorted(_called_names(functions[name])):
            if callee in functions and callee not in seen and callee != start:
                seen.append(callee)
                stack.append(callee)
    return seen


def _fetches(tree: ast.Module, name: str) -> bool:
    """Whether a module-level function opens a URL, directly or through one it calls."""
    functions = _functions(tree)
    for fn in [name, *_reachable(tree, name)]:
        for node in ast.walk(functions[fn]):
            if isinstance(node, ast.Attribute) and node.attr == "urlopen":
                return True
    return False


def settle_network_sources() -> list[str]:
    """The functions `settle()` calls that read the network, derived from the code.

    Only the ones settle() names itself: `fetch_json` is how they read, and
    the doc names the reader that says WHAT is read.
    """
    tree = ast.parse(BUILD_SCRIPT.read_text(encoding="utf-8"))
    functions = _functions(tree)
    direct = _called_names(functions["settle"]) & set(functions)
    return sorted(name for name in direct if _fetches(tree, name))


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


def test_the_derivation_finds_the_schedule_read() -> None:
    # Guards the derivation itself: if it found nothing, the doc check below
    # would pass on an empty list.
    assert settle_network_sources() == ["schedule_for"]
    tree = ast.parse(BUILD_SCRIPT.read_text(encoding="utf-8"))
    assert "load_team_games" not in _reachable(tree, "settle")


def test_schema_names_the_finals_source_settle_actually_calls() -> None:
    finals = sentences_about(r"\bfinals?\b")
    joined = " ".join(finals)
    for name in settle_network_sources():
        assert f"`{name}`" in joined, (
            f"settle() takes its finals through `{name}`, and SCHEMA.md's finals sentence does not name it: {finals}"
        )
    endpoint = site_module().NHL.split("://", 1)[1] + "/schedule"
    assert endpoint in joined, f"SCHEMA.md's finals sentence does not name the endpoint {endpoint}: {finals}"
    for sentence in finals:
        assert "load_team_games" not in sentence, (
            "SCHEMA.md says finals come through load_team_games; settle() never calls it: " + sentence
        )
        assert "boxscore" not in sentence.lower(), (
            "SCHEMA.md says finals come from the boxscore cache; settle() reads the NHL schedule: " + sentence
        )


# -- record.forward ----------------------------------------------------------


def test_the_builder_never_reads_closing_lines() -> None:
    tree = ast.parse(BUILD_SCRIPT.read_text(encoding="utf-8"))
    names = {
        getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "module", None)
        for node in ast.walk(tree)
    }
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not any(n and "closing_lines" in n for n in names)
    # And the board's record is load_record over forward_evidence.json.
    build_board = _functions(tree)["build_board"]
    calls = [
        node for node in ast.walk(build_board)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "load_record"
    ]
    assert len(calls) == 1
    assert "forward_evidence.json" in ast.unparse(calls[0])


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
    forward = sentences_about(r"record\.forward")
    joined = " ".join(forward)
    assert "forward_evidence.json" in joined, forward
    assert "`load_record`" in joined, forward
    for sentence in forward:
        assert "closing_lines" not in sentence, (
            "SCHEMA.md says record.forward comes from closing_lines; the builder never reads it: " + sentence
        )
