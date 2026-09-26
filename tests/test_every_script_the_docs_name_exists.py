"""Every script the documents tell a reader to run exists, with its flags.

CLAUDE.md's hard rule on writing off a prop line ("Before concluding a prop
line isn't offered, check per-bookmaker coverage including alternate lines")
named its tool as `scripts/run_provider_market_discovery.py --line-coverage`.
No such script has ever existed in this repository, and no script takes
`--line-coverage`. The coverage that rule asks for is
`reports/market_discovery.discover_coverage`, which
`scripts/run_provider_shadow.py` writes to `provider_market_discovery.md`,
run live by the Provider Market Discovery workflow.

A hard rule whose instruction cannot be followed is the same defect as the
phase guard's error naming a `--phase` flag the runner did not accept: the
reader obeying it hunts for their own mistake. So every `scripts/<name>.py`
the operating documents name must exist, and every flag written beside it
inside one backtick span must be one that script's source declares.
"""

from __future__ import annotations

import re

from nhl_betting_lab.config import PROJECT_ROOT

#: The documents a reader is told to act on.
DOCUMENTS = (
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "README.md",
    *sorted((PROJECT_ROOT / "docs").glob("*.md")),
)

SCRIPT = re.compile(r"scripts/[A-Za-z0-9_]+\.py")
#: A backticked command: a script path and whatever follows it in the span.
COMMAND = re.compile(r"`(scripts/[A-Za-z0-9_]+\.py)([^`]*)`")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def _named_scripts() -> dict[str, set[str]]:
    named: dict[str, set[str]] = {}
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for match in SCRIPT.finditer(text):
            named.setdefault(match.group(0), set()).add(document.name)
    return named


def test_the_documents_name_scripts_at_all() -> None:
    """A rule over an empty set checks nothing."""
    assert len(_named_scripts()) >= 5


def test_every_script_the_documents_name_exists() -> None:
    missing = {
        script: sorted(where)
        for script, where in _named_scripts().items()
        if not (PROJECT_ROOT / script).is_file()
    }
    assert missing == {}, (
        f"These documents name scripts that do not exist: {missing}"
    )


def test_every_flag_written_beside_a_script_is_one_it_declares() -> None:
    wrong: list[str] = []
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for match in COMMAND.finditer(text):
            script, rest = match.group(1), match.group(2)
            path = PROJECT_ROOT / script
            if not path.is_file():
                continue  # the test above names it
            source = path.read_text(encoding="utf-8")
            for flag in FLAG.findall(rest):
                if f'"{flag}"' not in source:
                    wrong.append(f"{document.name}: {script} {flag}")
    assert wrong == [], f"Flags no script declares: {wrong}"


def test_the_prop_coverage_rule_names_the_tool_that_answers_it() -> None:
    """The rule itself points at the real report, not only at a real file."""
    claude = " ".join(
        (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8").split()
    )
    assert "`scripts/run_provider_shadow.py" in claude
    assert "provider_market_discovery.md" in claude
    assert "discover_coverage" in claude
