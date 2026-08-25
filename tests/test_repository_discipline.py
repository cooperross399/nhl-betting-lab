"""Checks that keep the repository honest about itself.

None of these test behaviour. They test that the documentation, the command
reference, and the workflows have not drifted from the code — which is the
failure mode that makes every other document untrustworthy.
"""

from __future__ import annotations

import re

import pytest

from nhl_betting_lab.config import PROJECT_ROOT


SCRIPTS = sorted(
    path.name for path in (PROJECT_ROOT / "scripts").glob("*.py")
)
WORKFLOWS = sorted(
    path.name for path in (PROJECT_ROOT / ".github" / "workflows").glob("*.yml")
)


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_appears_in_the_command_reference(script: str) -> None:
    """A script nobody documented is a script nobody will run."""
    assert script in _read("README.md")


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_has_a_module_docstring(script: str) -> None:
    text = (PROJECT_ROOT / "scripts" / script).read_text(encoding="utf-8")

    assert '"""' in text.split("\n\n", 1)[0] or text.count('"""') >= 2


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_workflow_states_its_scope(workflow: str) -> None:
    """A workflow that does not say what it will not do is one nobody trusts."""
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )
    lowered = text.lower()

    assert "no bet" in lowered or "placed no bet" in lowered or "places no bet" in lowered


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_no_workflow_grants_write_access_to_contents(workflow: str) -> None:
    """Nothing here needs to push. Read plus issue comments is the whole job."""
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )

    assert "contents: write" not in text


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_workflow_pins_python_312(workflow: str) -> None:
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )
    if "setup-python" not in text:
        pytest.skip("This workflow does not run Python.")

    assert 'python-version: "3.12"' in text


def test_the_workflow_that_spends_the_most_is_never_scheduled() -> None:
    """Ten credits per market per event is not something a cron should decide."""
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert "schedule:" not in text
    assert "workflow_dispatch:" in text


def test_the_expensive_workflow_requires_a_credit_cap() -> None:
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert re.search(
        r"credit_cap:\s*\n\s*description:.*\n\s*type: string\s*\n\s*required: true",
        text,
    )


def test_every_doc_the_readme_links_to_exists() -> None:
    links = re.findall(r"\]\((docs/[^)]+|CLAUDE\.md)\)", _read("README.md"))

    assert links
    missing = [link for link in links if not (PROJECT_ROOT / link).is_file()]
    assert missing == []


def test_every_doc_claude_md_links_to_exists() -> None:
    links = re.findall(r"`(docs/[a-z0-9_]+\.md)`", _read("CLAUDE.md"))

    missing = [link for link in links if not (PROJECT_ROOT / link).is_file()]
    assert missing == []


def test_the_readme_states_the_current_honest_answer() -> None:
    text = _read("README.md")

    assert "no demonstrated edge" in text.lower()
    assert "never places a bet" in text


def _workflow_name(workflow: str) -> str:
    """The `name:` the workflow actually declares, not a guess from its
    filename. Title-casing a filename produced "Provider Policy Pr Gate",
    which is a test failing on its own spelling rather than on a real drift."""
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )
    match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
    assert match, f"{workflow} declares no name"
    return match.group(1).strip()


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_the_readme_names_every_workflow(workflow: str) -> None:
    assert _workflow_name(workflow) in _read("README.md")


def test_no_tracked_python_file_imports_a_betting_library() -> None:
    """A guard against the one dependency this project must never grow."""
    forbidden = ("betfair", "pinnacle_api", "selenium")
    offenders: list[str] = []
    for path in list((PROJECT_ROOT / "src").rglob("*.py")) + list(
        (PROJECT_ROOT / "scripts").glob("*.py")
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in forbidden:
            if re.search(rf"^\s*(import|from)\s+{name}", text, re.MULTILINE):
                offenders.append(f"{path.name}: {name}")

    assert offenders == []


def test_the_receipts_directory_holds_no_receipt() -> None:
    """Claude never writes one, not even a draft."""
    directory = PROJECT_ROOT / "data" / "manual" / "human_acceptance_receipts"

    assert list(directory.glob("*.json")) == []


def test_the_shipped_policy_allowlists_nothing() -> None:
    import json

    payload = json.loads(
        _read("data/manual/staging_provider_policy.json")
    )

    assert payload["allowed_provider_names"] == []
    assert payload["provider_allowlist_entries"] == {}
