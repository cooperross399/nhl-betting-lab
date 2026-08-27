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
    """One workflow pushes, to one branch. Everything else only reads.

    Gameday Refresh publishes each rendered card to the card-feed branch so
    the scheduled cloud routines can read it over plain git. That is the
    entire write surface: every `git push` in that workflow must target
    `refs/heads/card-feed` explicitly, and no other workflow may hold write
    access at all.
    """
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )

    if workflow != "gameday-refresh.yml":
        assert "contents: write" not in text
        return

    assert "contents: write" in text
    pushes = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\bgit push\b", line)
    ]
    assert pushes, "the write grant exists only for the card-feed publish"
    for line in pushes:
        assert "refs/heads/card-feed" in line


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


def test_every_receipt_on_disk_is_cited_by_the_shipped_policy() -> None:
    """Claude never writes a receipt, not even a draft — so the only receipt
    that may exist is one a human wrote and the policy actually cites. An
    orphan receipt is paperwork nothing verifies, and paperwork nothing
    verifies is how an approval gets faked."""
    import json

    directory = PROJECT_ROOT / "data" / "manual" / "human_acceptance_receipts"
    on_disk = {path.stem for path in directory.glob("*.json")}

    policy = json.loads(_read("data/manual/staging_provider_policy.json"))
    cited = {
        entry.get("evidence_receipt_id")
        for entry in policy.get("provider_allowlist_entries", {}).values()
    }

    assert on_disk <= cited, f"orphan receipt(s): {sorted(on_disk - cited)}"


def test_the_shipped_policy_is_structurally_disciplined() -> None:
    """Empty, or a real approval — never anything in between. Every allowed
    name has exactly one entry, every entry cites a receipt and a human
    reviewer, and no provider beyond the one the evidence was gathered
    against ever appears. The PR gate verifies the cited paperwork; this
    pins the shape."""
    import json

    payload = json.loads(
        _read("data/manual/staging_provider_policy.json")
    )

    names = payload["allowed_provider_names"]
    entries = payload["provider_allowlist_entries"]
    assert set(names) <= {"the_odds_api"}
    assert set(entries) == set(names)
    for entry in entries.values():
        assert entry.get("evidence_receipt_id")
        assert entry.get("reviewer_name")
        assert entry.get("required_markets")


def test_a_probe_does_not_rebuild_the_walk_forward_samples() -> None:
    """A probe asks one question of one event and nothing in the answer
    depends on the model. Making it wait for the full rebuild first was
    ceremony, and probing is the thing you do repeatedly. A buy of either kind
    does need the samples, because a buy has something to measure."""
    text = _read(".github/workflows/historical-props-purchase.yml")
    rebuild = text.index("Rebuild the results and the walk-forward samples")
    probe = text.index("- name: Probe retention")
    between = text[rebuild:probe]

    assert "if: ${{ inputs.mode != 'probe' }}" in between


def test_the_purchase_workflow_checks_the_quota_before_it_spends() -> None:
    text = _read(".github/workflows/historical-props-purchase.yml")
    quota = text.index("Report the quota before spending any of it")

    for later in ("- name: Probe retention", "- name: Buy a window"):
        assert text.index(later) > quota


def test_the_purchase_workflow_fails_when_the_quota_is_short() -> None:
    """Discovering the quota is short halfway through a buy wastes what was
    already spent."""
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert "--fail-under" in text


def test_a_slate_is_bounded_by_hours_not_by_the_utc_date() -> None:
    """A North American evening is the next day in UTC. Filtering on the UTC
    date kept four of fourteen games on 2026-01-10 — and the four it kept
    were the afternoon ones, which is a systematically different set."""
    text = _read("scripts/buy_historical_props.py")

    assert "window_start <= when.astimezone(timezone.utc) < window_end" in text
    assert "the four it kept were the afternoon games" in text


def test_the_two_workflows_can_restore_each_others_state() -> None:
    """They upload the same `gameday-state` artifact, so a first run of either
    should not refetch four thousand boxscores that already exist in one."""
    refresh = _read(".github/workflows/gameday-refresh.yml")
    purchase = _read(".github/workflows/historical-props-purchase.yml")

    assert "historical-props-purchase.yml" in refresh
    assert "gameday-refresh.yml" in purchase
    assert refresh.count("name: gameday-state") >= 1
    assert purchase.count("name: gameday-state") >= 1


def test_ci_measures_coverage_and_enforces_a_floor() -> None:
    """A floor catches a module arriving with no tests at all. It is not a
    target: setting it where the suite sits would reward tests written to move
    a percentage rather than to catch a defect."""
    import tomllib

    workflow = _read(".github/workflows/tests.yml")
    config = tomllib.loads(_read("pyproject.toml"))

    assert "coverage run" in workflow
    assert "coverage report" in workflow
    assert config["tool"]["coverage"]["report"]["fail_under"] == 90


def test_coverage_is_a_declared_dependency() -> None:
    """CI installs from requirements.txt; a step using a tool that is not
    there fails twenty minutes into a job."""
    assert "coverage" in _read("requirements.txt")


@pytest.mark.parametrize(
    "workflow", ["gameday-refresh.yml", "historical-props-purchase.yml"]
)
def test_state_restore_names_the_artifact_it_wants(workflow: str) -> None:
    """Without `--name`, `gh` puts each artifact in a subdirectory named after
    itself — the cache lands where nothing looks for it, the step still
    reports success, and the run silently refetches everything it already
    had."""
    text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )
    if "gh run download" not in text:
        pytest.skip("This workflow restores no state.")

    for line in text.splitlines():
        if "gh run download" in line:
            assert "--name" in line, line


def test_a_failed_restore_is_warned_about_rather_than_passed_over() -> None:
    """It is `continue-on-error`, so silence would look like success."""
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert "No boxscores were restored" in text


def test_an_empty_slate_is_not_reported_as_a_failure() -> None:
    """The off-season runs mid-June to early October. A red run every day of
    it is a red nobody reads on opening night."""
    text = _read(".github/workflows/gameday-refresh.yml")

    assert "empty_slate=true" in text
    assert "Not a fault" in text
    assert 'code" -eq 3' in text


def test_an_empty_slate_posts_no_card() -> None:
    """A comment a day saying "no games today" trains the reader to ignore
    the one that matters."""
    text = _read(".github/workflows/gameday-refresh.yml")

    assert "there is no card to post" in text


def test_the_daily_fetch_is_bounded_so_a_run_always_finishes() -> None:
    """At a quarter-second apiece, four thousand games cannot be fetched
    inside any sensible timeout, and a run killed at the timeout produces no
    card at all."""
    text = _read(".github/workflows/gameday-refresh.yml")

    assert "--max-games" in text
    assert "fills over consecutive days" in text


def test_a_thin_cache_is_reported_rather_than_silently_modelled() -> None:
    text = _read(".github/workflows/gameday-refresh.yml")

    assert "fitted on a thin history" in text
    assert "this resolves itself" in text


def test_team_prices_can_be_bought_from_the_workflow() -> None:
    """They went unmeasured while props were bought twice, because they were
    cheap enough to forget."""
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert "buy_team" in text
    assert "buy_historical_team_prices.py" in text


def test_purchases_are_serialised_and_never_cancelled() -> None:
    """Two racing would each restore the other's stale price file, and the
    second upload would silently discard the first run's spend. And a
    purchase that has spent credits must be allowed to finish."""
    text = _read(".github/workflows/historical-props-purchase.yml")

    assert "group: historical-purchase" in text
    assert "cancel-in-progress: false" in text


def test_the_linter_runs_in_ci_not_only_on_one_machine() -> None:
    """An undefined name in `Mapping` reached a branch this session because
    pyflakes ran locally and nowhere else."""
    assert "pyflakes" in _read(".github/workflows/tests.yml")
    assert "pyflakes" in _read("requirements.txt")


def test_the_evidence_bundle_is_assembled_where_the_evidence_is() -> None:
    """The shadow and coverage reports only exist where live runs happen, so
    a bundle assembled anywhere else correctly reports itself incomplete —
    and the authoritative one must therefore come from the workflow."""
    text = _read(".github/workflows/gameday-refresh.yml")

    assert "run_allowlist_evidence.py" in text
    assert "allowlist_evidence_bundle.md" in text


def test_every_wired_market_is_actually_fetched_somewhere() -> None:
    """The regulation three-way was modelled, sampled, priced and never
    requested — dead code on every production path, with the docs promising
    evidence that could never accumulate. Every market this lab declares must
    appear in a fetch list: bulk, per-event, or alternate."""
    from nhl_betting_lab.markets import ALL_MARKETS
    from nhl_betting_lab.providers import odds_api

    fetchable = (
        set(odds_api.BULK_PROVIDER_MARKETS)
        | set(odds_api.PER_EVENT_PROVIDER_MARKETS)
        | set(odds_api.ALTERNATE_PROVIDER_MARKETS)
    )
    shadow = _read("scripts/run_provider_shadow.py")

    for market in ALL_MARKETS:
        assert market.provider_key in fetchable, (
            f"{market.key} is wired but never fetched"
        )
    assert "PER_EVENT_PROVIDER_MARKETS" in shadow
