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

#: A path into THIS repository's `scripts/`. A path with anything before
#: `scripts/` (a sibling lab's `../epl-betting-lab/scripts/settle_card.py`,
#: or `web/scripts/x.py`) names another tree, and must not be checked here.
SCRIPT = re.compile(r"(?<![\w./-])scripts/[A-Za-z0-9_]+\.py")
#: A backticked command: a script path and whatever follows it in the span.
COMMAND = re.compile(r"`(scripts/[A-Za-z0-9_]+\.py)([^`]*)`")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def _script_paths(text: str) -> list[str]:
    return [match.group(0) for match in SCRIPT.finditer(text)]


def _named_scripts() -> dict[str, set[str]]:
    named: dict[str, set[str]] = {}
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for script in _script_paths(text):
            named.setdefault(script, set()).add(document.name)
    return named


def test_only_this_repositorys_script_paths_are_read() -> None:
    """A sibling lab's script is not this repository's, and must not false-fail."""
    text = (
        "Run `scripts/run_gameday_card.py`, as the football lab runs "
        "`../epl-betting-lab/scripts/settle_card.py` and "
        "/Users/cooperross/Projects/epl-betting-lab/scripts/fetch.py, "
        "and not web/scripts/build.py. "
        "(scripts/buy_historical_props.py) counts."
    )
    assert _script_paths(text) == [
        "scripts/run_gameday_card.py",
        "scripts/buy_historical_props.py",
    ]


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


def test_the_quoted_discovery_command_is_the_workflows_own() -> None:
    """The rule quotes the discovery step's command; it must carry the same flags.

    The first correction quoted it without `--overwrite-staging` and
    `--credit-cap`: run that way the script refuses to replace staging, or
    falls back to a cap of 190 that buys half the `--max-events 20` it names.
    """
    claude = " ".join(
        (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8").split()
    )
    quoted = [
        rest
        for script, rest in COMMAND.findall(claude)
        if script == "scripts/run_provider_shadow.py" and "--horizon-days 0" in rest
    ]
    assert len(quoted) == 1, quoted
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"
    ).read_text(encoding="utf-8")
    step = re.search(
        r"python scripts/run_provider_shadow\.py((?:[^\n]*\\\n)*[^\n]*)", workflow
    )
    assert step is not None
    assert set(FLAG.findall(quoted[0])) == set(FLAG.findall(step.group(1)))
