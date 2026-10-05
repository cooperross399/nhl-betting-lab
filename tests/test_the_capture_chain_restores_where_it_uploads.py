"""Every restore must unpack where its upload was rooted.

`upload-artifact` roots an artifact at the common ancestor of its paths, and
each artifact restore here is `gh run download <run> --name X --dir D`, run
directly or by `scripts/restore_state.py`. The two agree only while the
upload's root is D. On 2026-09-22 two `data/outputs` files were added to Line
Movement Capture's `line-movement` upload, which moved its root from
`data/processed` to `data/` while the restore still unpacked into
`data/processed`. Every restored capture would have landed one directory too
deep, each run would have started the day's file afresh, and continue-on-error
kept the job green. A capture cannot be collected again.

STAGE TWO (2026-10-05). Line Movement's chain is no longer an artifact. It
lives only on branch `movement` of the private repository
cooperross399/nhl-closing-lines, and no workflow uploads or restores
`line-movement`. The same failure can now happen in two other places, and
this file tests both:

- The chain's own round trip. `private_movement_chain.py push --processed-dir
  P` keeps `P/<store>/<day>.csv` as `<store>/<day>.csv`, and `pull --dest D`
  writes it back to `D/<store>/<day>.csv`. A round comes back where it was
  taken only while every chain command in Line Movement (pull, unseal, push,
  seal, verify) names one folder, the one the three capture scripts append
  to. Closing Lines' pull must land where its push to the closing-line store
  reads. The folders are read with the scripts' own argument parsers.
- The sealed fallback. A round whose private push failed is uploaded as the
  one file `round.enc` in `line-movement-sealed-N`. `unseal` downloads the zip
  of every such artifact and opens `round.enc` at its root, which works only
  while the upload is rooted at the folder `round.enc` sits in. A second path
  elsewhere would move the root up a level, as on 2026-09-22. The test seals
  a round with the workflow's own command, zips it the way upload-artifact
  roots it, serves the zip through an offline `gh`, and unseals it into a
  fresh folder with the workflow's own command. The day files must come back
  byte for byte where the next round's capture appends.

Not covered here: Gameday Refresh's CLV step pulls the chain into
$RUNNER_TEMP and passes that folder to the report through a bash array. This
file reads commands statically and cannot resolve an array.
tests/test_clv_reads_the_movement_chain.py replays that block instead. A
re-run's first attempt now comes back through the same pull and unseal. This
file checks where they unpack, not which rounds they find.

Every artifact restore in every workflow is paired with every upload of the
same name, and the root is derived from the upload's own paths. No comment
beside either step is trusted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_scripts import load_script

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402
import private_movement_chain as chain  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
DOWNLOAD = re.compile(r'gh run download \S+ --name ("?\$?\w[\w-]*"?) --dir (\S+)')
#: `scripts/restore_state.py` restores `--artifact X` into `--dest D` with
#: `gh run download --name X --dir D`, and `--also NAME=DIR` from the same run
#: the same way, so the same root rule applies to both.
HELPER = re.compile(r'restore_state\.py --artifact ("?\$?\w[\w-]*"?) --dest (\S+)')
ALSO = re.compile(r'restore_state\.py [^\n]*?--also ([\w-]+)=(\S+)')
LOOP = re.compile(r"for name in ([\w\- ]+); do")


def _uploads() -> dict[str, list[tuple[str, list[str]]]]:
    found: dict[str, list[tuple[str, list[str]]]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps", []) or []:
                if not str(step.get("uses", "")).startswith("actions/upload-artifact"):
                    continue
                given = step.get("with", {}) or {}
                paths = upload_paths(str(given.get("path", "")))
                found.setdefault(str(given.get("name")), []).append((path.name, paths))
    return found


def upload_paths(block: str) -> list[str]:
    """The search paths of a `path:` block, as upload-artifact reads them.

    Its glob skips blank lines, `#` comments and `!` exclusions. The EPL lab's
    uploads carry comments inside the block, and counting one as a path
    computes a root of "" and fails a restore that is correct.
    """
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith(("!", "#"))
    ]


def artifact_root(paths: list[str]) -> str:
    """The directory `upload-artifact` makes the artifact's root."""
    searched = [p.split("*")[0].rstrip("/") for p in paths]
    if len(searched) == 1:
        only = searched[0]
        return os.path.dirname(only) if Path(only).suffix else only
    return os.path.commonpath(searched)


def _restores() -> list[tuple[str, str, str]]:
    """(workflow, artifact name, directory) for every restore into the repo."""
    out = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        # Continuations joined first: a long invocation spans lines.
        text = re.sub(r"\\\s*\n\s*", " ", path.read_text(encoding="utf-8"))
        loop = LOOP.search(text)
        matches = [*DOWNLOAD.finditer(text), *HELPER.finditer(text), *ALSO.finditer(text)]
        for match in matches:
            name, directory = match.group(1).strip('"'), match.group(2)
            if directory.startswith("/"):
                continue  # a scratch download to inspect, not a restore in place
            names = loop.group(1).split() if name == "$name" and loop else [name]
            out.extend((path.name, n, directory) for n in names)
    return out


RESTORES = _restores()


def test_the_restores_were_actually_found():
    """A regex that stopped matching would make every case below vanish.

    Since stage two no workflow restores `line-movement`, so that anchor is
    gone. Each anchor here is a restore that one matcher finds: the helper's
    `--artifact`, its `--also`, and a `for name in ...` loop.
    """
    assert len(RESTORES) >= 8
    assert ("gameday-refresh.yml", "gameday-state", "data") in RESTORES
    assert ("publish-site.yml", "gameday-reports", "data/outputs") in RESTORES
    assert ("experiment-refresh.yml", "historical-props", "data") in RESTORES


@pytest.mark.parametrize("workflow,name,directory", RESTORES)
def test_a_restore_unpacks_where_its_artifact_was_rooted(workflow, name, directory):
    uploads = _uploads().get(name)
    assert uploads, f"{workflow} restores `{name}`, which no workflow uploads"
    for source, paths in uploads:
        assert artifact_root(paths) == directory, (
            f"{workflow} unpacks `{name}` into {directory}, but {source} roots it at "
            f"{artifact_root(paths)}: every restored file lands in the wrong place"
        )


@pytest.mark.parametrize(
    "paths,root",
    [
        (["data/processed/line_movement", "data/processed/deployment"], "data/processed"),
        (["data/processed/line_movement", "data/outputs/ladder_coherence.json"], "data"),
        (["data/outputs/a.json", "data/outputs/b.md"], "data/outputs"),
        (["dist/data/history"], "dist/data/history"),
        (["data/outputs/closing_line_value.md"], "data/outputs"),
    ],
)
def test_the_root_rule(paths, root):
    """The second case is the 2026-09-22 upload."""
    assert artifact_root(paths) == root


def test_a_comment_inside_a_path_block_is_not_a_path():
    block = """
        data/outputs/archive/automated_cards
        # Restored at the top of each run like the archive beside it.
        data/processed/epl_historical_matches.csv
        !data/processed/*.tmp
    """
    assert upload_paths(block) == [
        "data/outputs/archive/automated_cards",
        "data/processed/epl_historical_matches.csv",
    ]
    assert artifact_root(upload_paths(block)) == "data"


# --- stage two: the private chain --------------------------------------------

#: The three capture scripts, one per store the chain keeps. Each appends to
#: `capture_path(day)` unless the workflow gives it a `--processed-dir`, which
#: the test below holds to the same folder.
CAPTURES = ("capture_line_movement.py", "capture_deployment.py", "capture_line_combinations.py")
DAY = "2026-10-05"


def _steps(workflow: str, holding: str) -> list[dict]:
    """The steps of the one job in `workflow` with a step whose id is `holding`."""
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    (job,) = [j for j in document["jobs"].values()
              if any(s.get("id") == holding for s in j.get("steps", []) or [])]
    return job["steps"]


def _step(steps: list[dict], step_id: str) -> dict:
    (step,) = [s for s in steps if s.get("id") == step_id]
    return step


def _parsed(module, argv: list[str]) -> argparse.Namespace:
    """`argv` as the script's own `main` parses it. Its commands are replaced
    by a recorder, so nothing is pushed, pulled, sealed or opened."""
    seen: list[argparse.Namespace] = []
    with pytest.MonkeyPatch.context() as patch:
        for command in ("push", "pull", "verify", "seal", "unseal"):
            if hasattr(module, command):
                patch.setattr(module, command, seen.append)
        module.main(argv)
    (args,) = seen
    return args


def _invocations(steps: list[dict], script: str, module) -> list[tuple[list[str], argparse.Namespace]]:
    """(argv, parsed) for every `python scripts/<script>` line in the steps'
    run blocks. Comments are skipped, and so is everything from `||` on."""
    marker = f"python scripts/{script} "
    found = []
    for step in steps:
        block = re.sub(r"\\\s*\n\s*", " ", str(step.get("run", "")))
        for line in block.splitlines():
            if line.strip().startswith("#") or marker not in line:
                continue
            argv = shlex.split(line.split(marker, 1)[1].split("||")[0])
            found.append((argv, _parsed(module, argv)))
    return found


def _folder(args: argparse.Namespace) -> str:
    """The folder a chain or store command reads, or writes into."""
    return args.dest if args.command in ("pull", "unseal") else args.processed_dir


def _appended(name: str) -> Path:
    """Where the capture script `name` appends today's day file, relative to
    the checkout."""
    return load_script(name).capture_path(DAY).relative_to(PROJECT_ROOT)


LINE_MOVEMENT = _steps("line-movement.yml", "private_push")


def test_every_chain_command_names_the_folder_the_captures_append_to():
    """Push keeps `P/<store>/<day>.csv` and pull writes `D/<store>/<day>.csv`,
    so a round comes back where it was taken only while every chain command
    names the folder the captures append to. A push pointed at a folder with
    no day file says "nothing to push" and exits 0, so the round is neither
    pushed nor sealed; the check after it can only report the loss."""
    calls = _invocations(LINE_MOVEMENT, "private_movement_chain.py", chain)
    assert sorted(args.command for _, args in calls) == ["pull", "push", "seal", "unseal", "verify"]
    appended = {_appended(name) for name in CAPTURES}
    assert {path.parent.name for path in appended} == set(chain.STORES), (
        "the chain keeps a different set of stores than the captures write"
    )
    roots = {path.parent.parent for path in appended}
    assert len(roots) == 1, roots
    for _, args in calls:
        assert Path(_folder(args)) in roots, (
            f"`{args.command}` names {_folder(args)}, but the captures append under "
            f"{next(iter(roots))}: every round lands somewhere the next one does not read"
        )
    for name in CAPTURES:
        runs = [shlex.split(line.split(f"scripts/{name}", 1)[1])
                for step in LINE_MOVEMENT
                for line in re.sub(r"\\\s*\n\s*", " ", str(step.get("run", ""))).splitlines()
                if f"python scripts/{name}" in line and not line.strip().startswith("#")]
        assert runs, f"no step runs {name}"
        for argv in runs:
            given = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--processed-dir"]
            given += [arg.split("=", 1)[1] for arg in argv if arg.startswith("--processed-dir=")]
            assert all(Path(folder) in roots for folder in given), (
                f"{name} is pointed at {given}, away from the folder the chain keeps"
            )


def test_the_line_movement_restore_checks_the_stores_the_chain_keeps():
    """The restore's own check names three day-stores, in the folder the pull
    fills. Each must be a store the chain keeps."""
    restore = _step(LINE_MOVEMENT, "restore")
    block = restore["run"]
    checked = re.search(r"for store in ([\w ]+); do", block).group(1).split()
    looked = re.search(r'ls -la "(\S+)/\$store/\$DAY\.csv"', block).group(1)
    (pull,) = [args for _, args in _invocations([restore], "private_movement_chain.py", chain)
               if args.command == "pull"]
    assert checked
    assert set(checked) <= set(chain.STORES)
    assert looked == pull.dest


def test_closing_lines_pulls_the_chain_where_its_push_reads_it():
    """The closing-line store's push reads `<processed-dir>/line_movement`.
    Until stage two this was the `line-movement` artifact restore, paired
    above. Now it is the private pull, which must land in that folder."""
    steps = _steps("closing-lines.yml", "handoff")
    (pull,) = [args for _, args in _invocations(steps, "private_movement_chain.py", chain)]
    (push,) = [args for _, args in _invocations(steps, "private_closing_store.py", store)]
    assert (pull.command, push.command) == ("pull", "push")
    assert pull.dest == push.processed_dir
    assert store.MOVEMENT_DIRNAME in chain.STORES, "the store reads a folder the chain does not keep"


# --- stage two: the sealed fallback -------------------------------------------

RUNNER_TEMP = "${{ runner.temp }}"
RUN_ATTEMPT = "${{ github.run_attempt }}"
OFFLINE_GH = """#!/bin/sh
case "$*" in
  */zip*) exec cat "$SEALED_ZIP" ;;
  *actions/artifacts*) exec cat "$SEALED_LISTING" ;;
esac
echo "offline gh: unexpected call: $*" >&2
exit 1
"""


def _upload_artifact(paths: list[str], archive: Path) -> Path:
    """The zip upload-artifact builds: every file the paths find, named
    relative to the root `artifact_root` derives. A path that finds nothing
    adds nothing, and a set that finds nothing at all is the upload's
    `if-no-files-found: error`."""
    root = artifact_root(paths)
    files: list[Path] = []
    for path in map(Path, paths):
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file()))
    assert files, f"the sealed upload finds no file at {paths}: the seal wrote somewhere else"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in files:
            zipped.write(path, os.path.relpath(path, root))
    return archive


def test_a_sealed_round_comes_back_where_the_next_round_appends(tmp_path, monkeypatch):
    runner_temp, first, second, offline = (tmp_path / d for d in ("runner-temp", "round-1", "round-2", "bin"))
    for folder in (runner_temp, first, second, offline):
        folder.mkdir()
    monkeypatch.setenv(chain.KEY_ENV, secrets.token_hex(16))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))

    # This round's captures, where the three capture scripts append them.
    kept = {}
    for n, name in enumerate(CAPTURES):
        rel = _appended(name)
        (first / rel).parent.mkdir(parents=True, exist_ok=True)
        (first / rel).write_bytes(f"captured_at,value\n2026-10-05T14:00:00Z,{n}\n".encode())
        kept[rel] = (first / rel).read_bytes()

    # The push failed: "Seal this round when the private push failed".
    (seal,) = _invocations([_step(LINE_MOVEMENT, "seal")], "private_movement_chain.py", chain)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(first))
    monkeypatch.chdir(first)
    assert chain.main([os.path.expandvars(arg) for arg in seal[0]]) == chain.EXIT_OK

    # "Keep the sealed round", as upload-artifact roots it.
    given = _step(LINE_MOVEMENT, "sealed_upload")["with"]
    name = str(given["name"]).replace(RUN_ATTEMPT, "1")
    paths = [p.replace(RUNNER_TEMP, str(runner_temp)) for p in upload_paths(str(given["path"]))]
    assert "${{" not in name + "".join(paths), "an expression this test does not render"
    archive = _upload_artifact(paths, tmp_path / "artifact.zip")

    # The next round, on a fresh runner: "Restore today's captures" unseals
    # every sealed artifact GitHub lists.
    listing = tmp_path / "listing.jsonl"
    listing.write_text(json.dumps({
        "id": 7, "name": name, "expired": False, "created_at": "2026-10-05T14:05:00Z",
        "workflow_run": {"id": 1234, "head_branch": "main"},
    }) + "\n")
    (offline / "gh").write_text(OFFLINE_GH)
    (offline / "gh").chmod(0o755)
    monkeypatch.setenv("SEALED_ZIP", str(archive))
    monkeypatch.setenv("SEALED_LISTING", str(listing))
    monkeypatch.setenv("PATH", f"{offline}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GITHUB_REPOSITORY", "cooperross399/nhl-betting-lab")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(second))
    monkeypatch.chdir(second)
    (unseal,) = [argv for argv, args in _invocations([_step(LINE_MOVEMENT, "restore")],
                                                     "private_movement_chain.py", chain)
                 if args.command == "unseal"]
    assert chain.main(unseal) == chain.EXIT_OK
    for rel, body in kept.items():
        assert (second / rel).is_file(), f"the sealed {rel} did not come back where the capture appends"
        assert (second / rel).read_bytes() == body
