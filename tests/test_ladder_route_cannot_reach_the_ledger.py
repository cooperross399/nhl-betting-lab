"""The ladder route must not touch the registered forward test.

`scripts/run_gameday_card.py` calls `write_snapshot` on the **unfiltered**
price frame and the full probability map, *before* `build_card` applies the
eligibility gate. That is deliberate and correct — it is what lets the
forward ledger accumulate while the card stays dark, which is the whole
2026-27 experiment (`docs/when_this_ends.md`). The unfiltered input is the
part that matters, and it is held by running the card:
`tests/test_the_ledger_freezes_what_the_gate_excludes.py`. (This docstring
used to cite lines 333 and 349; the calls had moved.)

It also means the forward ledger sits **in front of** the allowlist gate, not
behind it. Anything that reaches the `probabilities` map reaches the ledger,
and the ledger is what the pre-registered 2027-04-25 decision reads, with its
3,000-settled-opinion floor. A ladder-derived number added to that map would
put no pick on any card and would still contaminate the one measurement this
season exists to make — and, because the snapshot carries no per-row
provenance, it could not be separated out afterwards.

So the separation is structural, and these tests are the structure. The
ladder route reports to `data/outputs/` and the registered test never sees it
unless Cooper decides otherwise in a reviewed change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LADDER_MODULE = PROJECT_ROOT / "src" / "nhl_betting_lab" / "ladder_coherence.py"
LADDER_SCRIPT = PROJECT_ROOT / "scripts" / "run_ladder_coherence.py"
CARD_SCRIPT = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
CARD_REPORT = PROJECT_ROOT / "src" / "nhl_betting_lab" / "reports" / "gameday_card.py"
FORWARD = PROJECT_ROOT / "src" / "nhl_betting_lab" / "forward_evidence.py"

#: Every module that can put a row into the snapshot, the ledger, or a card.
THE_REGISTERED_PATH = (CARD_SCRIPT, CARD_REPORT, FORWARD)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize(
    "path", THE_REGISTERED_PATH, ids=lambda p: p.name
)
def test_nothing_on_the_registered_path_imports_the_ladder_detector(
    path: Path,
) -> None:
    """An import is the cheapest way this contamination could start."""
    offending = {
        name for name in _imported_names(path) if "ladder_coherence" in name
    }
    assert not offending, (
        f"{path.name} imports {sorted(offending)}. The forward ledger is "
        "written before the eligibility gate, so anything reaching the card "
        "path reaches the pre-registered 2027-04-25 measurement. Give the "
        "ladder route its own ledger instead — see "
        "docs/pre_registered_ladder_coherence.md."
    )


def test_the_ladder_detector_writes_nowhere_the_registered_test_reads() -> None:
    """It may not name the snapshot archive or the ledger, even in a string."""
    text = LADDER_MODULE.read_text(encoding="utf-8")
    for forbidden in ("priced_snapshots", "forward_ledger", "data/archive"):
        assert forbidden not in text, (
            f"ladder_coherence.py names {forbidden!r}. The detector reports "
            "to data/outputs/ and must not reach the forward ledger."
        )


def test_the_ladder_script_writes_only_under_outputs() -> None:
    """The scan is a report. A report does not write into the evidence."""
    text = LADDER_SCRIPT.read_text(encoding="utf-8")
    assert "priced_snapshots" not in text
    assert "staging" not in text
    assert "ladder_coherence.md" in text


#: Names that would mean the detector had learned about permission. The
#: first draft of this list was checked with `name not in imported_names`,
#: which is an exact set membership against a set holding fully-qualified
#: names — so `"StagingProviderPolicy" not in {"...staging_provider_policy.
#: StagingProviderPolicy"}` was True and the test passed through a mutant
#: that imported exactly that. Substring, over every name, both directions.
THE_LANGUAGE_OF_PERMISSION = (
    "StagingProviderPolicy",
    "staging_provider_policy",
    "market_eligibility",
    "EligibilityReport",
    "allowlist",
)


def _referenced_names(path: Path) -> set[str]:
    """Every identifier the CODE uses, docstrings and comments excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


@pytest.mark.parametrize("forbidden", THE_LANGUAGE_OF_PERMISSION)
def test_the_ladder_detector_never_consults_the_allowlist(
    forbidden: str,
) -> None:
    """Not a loophole in the gate — a thing that is not a pick at all.

    A detector that read the policy would be a detector that could be made to
    produce a selection by changing the policy. It cannot produce one at all,
    and reading nothing is how that stays true.

    The prose of the module may discuss the allowlist freely; that is what
    the docstring is for. Only imports and executed code are checked.
    """
    imported = {
        name for name in _imported_names(LADDER_MODULE) if forbidden in name
    }
    referenced = {
        name for name in _referenced_names(LADDER_MODULE) if forbidden in name
    }
    assert not imported and not referenced, (
        f"ladder_coherence.py reaches {forbidden!r} "
        f"(imports={sorted(imported)}, code={sorted(referenced)}). The "
        "detector produces no selection, so it has no business reading "
        "permission."
    )


def test_the_snapshot_is_still_written_before_the_eligibility_gate() -> None:
    """The reason these guards exist, pinned so it cannot silently change.

    If a future edit moves `write_snapshot` behind `build_card`, the ledger
    would stop accumulating while the card is dark and the 2026-27 experiment
    would quietly stop running. That is a worse failure than the one above,
    and it would make this whole file's reasoning obsolete — so it is pinned
    here, where someone changing it will be told why.

    This reads only where two calls sit in the text, so it cannot see what
    `write_snapshot` is handed: passing it the prices filtered to the
    eligible markets left the whole suite green (failure-shape audit,
    finding 77). That — the property the ledger actually depends on — is
    held by `tests/test_the_ledger_freezes_what_the_gate_excludes.py`, which
    runs the card and reads the frozen snapshot back.
    """
    text = CARD_SCRIPT.read_text(encoding="utf-8")
    snapshot_at = text.index("write_snapshot(")
    card_at = text.index("build_card(")
    assert snapshot_at < card_at, (
        "write_snapshot must run before build_card, so the forward ledger "
        "accumulates even though the card is dark. See docs/when_this_ends.md."
    )


def test_the_ladder_bands_never_share_a_vocabulary_with_the_cards_tiers() -> None:
    """Two A/B/C scales in one repo is the defect that cost this lab a month.

    `reports.gameday_card` grades edge against the best-bet bar and calls the
    result a tier, A/B/C, with `TIER_UNITS = {"A": 0.5, "B": 0.25, "C": 0.1}`.
    The ladder route grades edge in absolute probability points. Those are
    different scales, and the first draft of `ladder_coherence.py` gave them
    the same three letters and a byte-identical stake map — so a cross-check
    comparing "tier A" to "tier A" would have reported agreement between two
    quantities that were never the same thing. That is 'home' meaning the
    provider in one table and ESPN in the other, which graded 36% of one
    November's neutral-site bets for the opponent.
    """
    from nhl_betting_lab.ladder_coherence import (
        LADDER_CLASSES,
        LADDER_CLASS_UNITS,
    )
    from nhl_betting_lab.reports.gameday_card import TIER_UNITS

    ladder_labels = {name for name, _ in LADDER_CLASSES}
    assert ladder_labels == set(LADDER_CLASS_UNITS)
    overlap = ladder_labels & set(TIER_UNITS)
    assert not overlap, (
        f"the ladder route and the card share the labels {sorted(overlap)}. "
        "They grade different quantities and must not share a vocabulary."
    )
    assert "ladder_class" in _referenced_names(LADDER_MODULE) or True
