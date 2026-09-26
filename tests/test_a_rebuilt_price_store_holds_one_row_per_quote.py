"""A rebuilt price store holds one row per quote per window, as a bought one does.

`scripts/rebuild_price_files.py` reconstructs the price CSVs from the raw
cache, and it is the recovery path this lab has leaned on twice. It
deduplicated what it rebuilt on the WHOLE ROW, while every purchase writes
through `stores.dedupe_prices`, which keys on the quote plus the window
`label_phases` derives. The two disagree exactly where it matters: two cached
responses of one event inside one window, fetched five minutes apart, carry
two different `snapshot` and `fetched_at` stamps, so the whole-row rule kept
both copies of every quote. A rebuilt store then differed from the store the
purchase wrote, every "another book's quote" count was inflated, and the
best-price collapse could take the better of two moments inside one window —
a price nobody held at one instant.

These tests run the real script on a scratch cache and hold it to the rule
the purchase obeys: a second response inside one window collapses onto the
first, a second WINDOW never does, and the file written is already a fixed
point of `dedupe_prices`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

from nhl_betting_lab.stores import PRICE_IDENTITY, dedupe_prices, label_phases

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 23:00Z face-off: 13:30Z and 13:35Z are both ~9.5 hours out (`card`);
# 19:00Z is 4.0 hours out (`late`).
COMMENCE = "2025-11-01T23:00:00Z"
CARD_FIRST = "2025-11-01T13:30:00Z"
CARD_SECOND = "2025-11-01T13:35:00Z"
LATE = "2025-11-01T19:00:00Z"


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prop_event(over_price: int) -> dict:
    return {
        "id": "e1",
        "commence_time": COMMENCE,
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "player_shots_on_goal",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Test Player",
                                "price": over_price,
                                "point": 2.5,
                            },
                            {
                                "name": "Under",
                                "description": "Test Player",
                                "price": -110,
                                "point": 2.5,
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _team_event() -> dict:
    return {
        "id": "e1",
        "commence_time": COMMENCE,
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
                            {"name": "Toronto Maple Leafs", "price": -130},
                            {"name": "Boston Bruins", "price": 110},
                        ],
                    }
                ],
            }
        ],
    }


def _write(cache: Path, stamp: str, data: object) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    name = f"e1_{stamp.replace(':', '').replace('-', '')}.json"
    (cache / name).write_text(
        json.dumps({"timestamp": stamp, "data": data}), encoding="utf-8"
    )


def _rebuild(tmp_path: Path) -> Path:
    module = load_script("rebuild_price_files.py")
    out = tmp_path / "out"
    code = module.main(["--raw-dir", str(tmp_path), "--processed-dir", str(out)])
    assert code == 0
    return out


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False)


def test_two_responses_inside_one_window_rebuild_to_one_row_per_quote(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "historical_props"
    _write(cache, CARD_FIRST, _prop_event(-110))
    _write(cache, CARD_SECOND, _prop_event(-105))

    rebuilt = _read(_rebuild(tmp_path) / "historical_prop_prices.csv")

    # Two quotes (over and under), each fetched twice inside `card`.
    assert len(rebuilt) == 2, rebuilt
    assert set(label_phases(rebuilt)["phase"]) == {"card"}
    # The later response wins, as `keep="last"` gives it on a purchase that
    # appends a newer fetch to the store.
    over = rebuilt[rebuilt["selection"] == "over"]
    assert over["american_odds"].tolist() == [-105]
    assert over["snapshot"].tolist() == [CARD_SECOND]


def test_a_second_window_is_never_collapsed_onto_the_first(tmp_path: Path) -> None:
    cache = tmp_path / "historical_props"
    _write(cache, CARD_FIRST, _prop_event(-110))
    _write(cache, LATE, _prop_event(-110))

    rebuilt = _read(_rebuild(tmp_path) / "historical_prop_prices.csv")

    # Identical quotes at two moments in two windows are two rows each.
    assert len(rebuilt) == 4, rebuilt
    assert sorted(label_phases(rebuilt)["phase"]) == ["card", "card", "late", "late"]


def test_the_rebuilt_prop_store_is_already_what_dedupe_prices_would_keep(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "historical_props"
    _write(cache, CARD_FIRST, _prop_event(-110))
    _write(cache, CARD_SECOND, _prop_event(-105))
    _write(cache, LATE, _prop_event(-120))

    rebuilt = _read(_rebuild(tmp_path) / "historical_prop_prices.csv")

    again = dedupe_prices(rebuilt)
    assert len(again) == len(rebuilt) == 4
    identity = label_phases(rebuilt)[[*PRICE_IDENTITY, "phase"]].astype(str)
    assert not identity.duplicated().any()


def test_the_team_store_obeys_the_same_rule(tmp_path: Path) -> None:
    cache = tmp_path / "historical_team_prices"
    # The team cache holds a slate per snapshot, as a list of events.
    _write(cache, CARD_FIRST, [_team_event()])
    _write(cache, CARD_SECOND, [_team_event()])
    _write(cache, LATE, [_team_event()])

    rebuilt = _read(_rebuild(tmp_path) / "historical_team_prices.csv")

    # Home and away moneyline, once in `card` and once in `late`.
    assert len(rebuilt) == 4, rebuilt
    assert sorted(label_phases(rebuilt)["phase"]) == ["card", "card", "late", "late"]
    assert len(dedupe_prices(rebuilt)) == len(rebuilt)
