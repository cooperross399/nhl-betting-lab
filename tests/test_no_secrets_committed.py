"""Repository hygiene: no credential may reach a tracked file.

These tests run against the files git actually tracks, so they fail the build
if a secret is ever committed — including by a future change that means well.
They deliberately do not read `.env`: the point is to prove nothing *else*
contains a credential, and reading the real key here would be the very leak
being guarded against.

Ported from the EPL lab, and then rebuilt after the audit of the five labs
found that the port had five holes, each of which let a real credential be
committed with the suite green. Do not read this file as a warranty; read the
list, and read `test_the_gaps_this_guard_still_has_are_the_ones_written_down`
for what is still open:

* the hex scan skipped any file whose NAME contained "checksum" or
  "receipt" — so identical bytes passed as `week3_receipt.md` and failed as
  `week3.md`, and the blind spot sat on the acceptance receipts, whose whole
  job is provenance;
* `HEX_KEY` was fenced with `\\b`, which will not open beside `_` because `_`
  is a word character, so `<key>_odds.json` — the provider cache's own naming
  convention — hid a key, and the class was lowercase-only, so an uppercased
  copy of the same key was not a key;
* only file BODIES were scanned, and only after `path.is_file()`. A key in a
  filename needed no decoding and was read by nothing; a tracked symlink whose
  target was the key was dropped by `is_file()` and read by nothing;
* the exemption harvest read `path.name.split("_")[0]` off EVERY tracked file
  before any directory restriction, so a decoy `<key>_x.md` at the root
  nominated the key into the exemption set and turned it green everywhere;
* `ASSIGNMENT` knew `NAME=value` and nothing else. `os.environ["NAME"] = v`,
  `NAME: v` in YAML, `NAME := v`, and a U+00A0 after the `=` were all
  invisible, and every `.md`, `.rst` and `.txt` was exempt from the
  assignment scan outright unless the value happened to be 32 hex characters.

Every hole above is pinned by a test that fails against the module as it was.
Several rules overlap, so "fails if you revert one line" is a stronger claim
than the true one; each test says which rule it was run against.

THE LESSON, stated once: a guard that greps for a spelling proves only that
the spelling is absent. Every rule here is fenced with lookarounds rather than
word boundaries, keyed on a shape rather than an enumeration where it can be,
and attacked with three spellings of the same leak before it is believed. Where
a gap could not be closed cheaply it is written into the known-gaps test rather
than papered over in a docstring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers.env_file import ENV_FILENAME, PROVIDER_ENV_ALLOWLIST


#: Obvious placeholders that must never be mistaken for a real credential.
#: This is the whole allowance documentation gets. There used to be a second,
#: much wider one — any `.md`, `.rst` or `.txt` value that was not 32 hex
#: characters was skipped outright, so a real key of any other shape could be
#: assigned in prose and pass. Prose that wants to show the form of a command
#: writes a placeholder from this set or a reference (`$VAR`, `<your-key>`,
#: `${{ secrets.X }}`), and both stay allowed everywhere.
PLACEHOLDERS = {
    "your-secret-key",
    "your-api-key",
    "test-secret-that-must-not-be-written",
    "env-file-secret-that-must-never-be-written",
    "shadow-test-secret-never-write",
    "discovery-secret-must-not-be-written",
    "props-secret-must-not-be-written",
    "already-exported-value",
    "${{",
}

#: A 32-hex-character run is the shape of an Odds API key.
#:
#: Fenced with lookarounds, not `\b`. `\b` will not open beside `_` because
#: `_` is a word character, and the provider cache names its files
#: `<event id>_odds.json` — the convention an attacker would copy. One
#: underscore of adjacent context therefore hid a real key from the old
#: matcher, in a body and in a name. The lookarounds still refuse to fire
#: inside a longer hex run, so a SHA-256 is not a finding.
#:
#: `A-F` as well as `a-f` because an uppercased copy of a key is the same key.
#: While the class was lowercase-only, `KEY = "<the key, uppercased>"` was
#: invisible — found by attacking the matcher, not by reading it.
HEX_KEY = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32}(?![0-9A-Fa-f])")

#: ...and it is also the shape of an Odds API **event id**, a real collision:
#: cached responses and bought-price tables are full of them. The exemption is
#: by VALUE — every event id the provider actually recorded in a response
#: body or a table column — and never by directory or by filename. A body is
#: written by the provider; a filename is chosen by whoever adds the file.
_EVENT_ID_KEYS = ("id", "event_id")

#: Where a recorded event id may be SPENT: the provider cache and the reports
#: rendered from it. Nothing else has an innocent reason to carry one.
#:
#: This is a spend rule and only a spend rule. Creation is the provider
#: cache's privilege alone — `_collect_event_ids` harvests from `data/raw/`
#: and nowhere else. It used to harvest filename stems from EVERY tracked
#: file before any directory check, so a decoy `<key>_x.md` at the root
#: nominated the key into the exemption set and turned it green everywhere.
#: A report this repository writes may spend an exemption; it must not create
#: one. `.gitignore` makes `data/raw/` untrackable, so on the real repository
#: the live exemption set is empty and every 32-hex run in a tracked file is a
#: finding — the fail-closed direction.
EXEMPT_SCOPE = ("data/raw/", "data/outputs/")

#: A 32-hex digest that is not an event id, exempted by recorded value with a
#: comment naming the file it came from. Empty: no tracked file needs one.
#: This replaces the by-name skip of "checksum" and "receipt" files, which
#: exempted every 32-hex run in such a file, a real key included.
RECORDED_DIGESTS: frozenset[str] = frozenset()

#: The GitHub secret holding this lab's provider credential. The NAME belongs
#: in the repository; the VALUE never does.
GITHUB_SECRET_NAME = "NHL_ODDS_API_KEY"

#: The shape of a credential variable name. A matcher that knows `_API_KEY`
#: alone goes quiet on `_APIKEY` and `_API_TOKEN` the day something is
#: renamed, and goes quiet silently.
CREDENTIAL_NAME_SHAPE = re.compile(r"\b[A-Z][A-Z0-9_]*_(?:API_KEY|APIKEY|API_TOKEN)\b")

#: Every credential-ish variable name a tracked file may mention but never
#: assign: the secret's name, plus every allowlisted `.env` name that is
#: shaped like a credential. `NHL_ODDS_API_BASE_URL` is allowlisted and is not
#: one — a URL is not a secret — and treating it as one would flag the
#: example file. `test_no_credential_name_in_the_repository_is_unknown_to_
#: this_guard` fails the build if a credential-shaped name appears anywhere in
#: the tree and is missing from here.
CREDENTIAL_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            GITHUB_SECRET_NAME,
            *(name for name in PROVIDER_ENV_ALLOWLIST if CREDENTIAL_NAME_SHAPE.fullmatch(name)),
        )
    )
)


def _collect_event_ids(paths: Iterable[Path], root: Path) -> tuple[set[str], set[str]]:
    """Split recorded event ids by how strong the evidence for them is.

    `content_ids` come out of a response body or a table cell — the provider
    put them there, so they are a record. `name_ids` come off a filename,
    which anyone can choose, so they are a claim. Only `content_ids` may
    exempt a hex run; `name_ids` exists to be checked against it. Both are
    read from `data/raw/` and nowhere else.
    """
    content_ids: set[str] = set()
    name_ids: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _EVENT_ID_KEYS and isinstance(value, str):
                    if HEX_KEY.fullmatch(value):
                        content_ids.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("data/raw/"):
            # Creating an exemption is the provider cache's privilege alone.
            continue
        stem = path.name.split("_")[0]
        if HEX_KEY.fullmatch(stem):
            name_ids.add(stem)
        if path.suffix == ".json":
            try:
                walk(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        elif path.suffix == ".csv":
            try:
                header, *rows = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError, ValueError):
                continue
            columns = [name.strip() for name in header.split(",")]
            wanted = [index for index, name in enumerate(columns) if name in _EVENT_ID_KEYS]
            if not wanted:
                continue
            for row in rows:
                cells = row.split(",")
                for index in wanted:
                    if index < len(cells) and HEX_KEY.fullmatch(cells[index].strip()):
                        content_ids.add(cells[index].strip())
    return content_ids, name_ids


def _exempt_hex_values() -> set[str]:
    """Every 32-hex literal this repository has a recorded reason to allow."""
    content_ids, _ = _collect_event_ids(_tracked_files(), PROJECT_ROOT)
    return content_ids | set(RECORDED_DIGESTS)


#: `apiKey=` FOLLOWED BY A VALUE is a leak; the bare token is not, because it
#: appears in the redaction regex and in tests asserting it is absent. The
#: parameter name is a family (`apiKey`, `apikey`, `api_key`, `api-key`, any
#: case) and the value class admits `-` and `_`, because the narrower
#: `[A-Za-z0-9]{8,}` could not match `sk-live-…`, the shape this file uses as
#: its own worked example. The first character stays alphanumeric so
#: `apiKey=[redacted]` is still not a match.
API_KEY_PARAM = re.compile(r"api[_-]?key=[A-Za-z0-9][A-Za-z0-9_-]{7,}", re.IGNORECASE)

#: Punctuation that may sit between a credential name and the operator that
#: gives it a value: the closing half of a quote, a subscript, a code span, an
#: emphasis marker, or an HTML tag. A shape, not an enumeration — six listed
#: characters missed `**NAME**: <key>` and `<code>NAME</code>: <key>`. Bounded
#: at eight so it cannot walk across a line. Newline is excluded on purpose:
#: `NAME` on one line and `=` on the next is not an assignment, which is what
#: keeps `.env.example` green.
#:
#: `!`, `<` and `>` are excluded from the character class (a tag still comes
#: in through the tag alternative), and the operator refuses a second `=`
#: behind it, because `environment["NAME"] == SECRET`, `NAME != x` and
#: `NAME >= 5` are comparisons, and the first of them is what this
#: repository's own tests write. Found by running the widened rule over the
#: tracked corpus, which is the only way a false positive is ever found.
_CLOSERS = r"(?:</?[A-Za-z][A-Za-z0-9]*[^<>\n]{0,64}>|[^0-9A-Za-z\n=:,|!<>]){0,8}"

#: A horizontal blank, agreeing with `\S` about what a blank is. `[ \t]*` is
#: ASCII and `\S` is Unicode-aware, and a U+00A0 after the operator fell in
#: the gap between them: neither consumed it, no match opened, and
#: `export NAME=<U+00A0><key>` gave a fully green suite. `[^\S\r\n]*` is every
#: character `\S` refuses minus the line breaks, so the two classes partition
#: the input.
_BLANK = r"[^\S\r\n]*"

#: The rest of the line after the operator, captured through a lookahead so
#: the match ends at the operator (a consumed value would swallow a nested
#: occurrence). Bounded, because unbounded the scan went quadratic on a line
#: carrying the name two thousand times — a guard slow enough to look hung is
#: a guard someone switches off.
_REST_OF_LINE = r"(?=(.{0,512}))"

_NAMES = "|".join(re.escape(name) for name in CREDENTIAL_NAMES)

#: `NAME=value` where NAME is a credential variable, with everything the old
#: single-character rule missed: `_CLOSERS` between the name and the operator
#: (so `os.environ["NAME"] = …`, the canonical Python spelling, is a finding),
#: the operator family `[:?+]?=` (Make's `:=`/`?=`, shell's `+=` and
#: `${NAME:=literal}`), `_BLANK` on both sides, the whole rest of the line
#: rather than its first token, and `re.IGNORECASE` because a lowercased
#: spelling of the name is the same handle on the same value.
#:
#: The fence is `(?<![A-Za-z0-9])` and not `\b`, because `\b` will not open
#: between `_` and a letter and the Markdown emphasis `_NAME_` was unreachable
#: however wide the closers got.
ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9])(" + _NAMES + r")" + _CLOSERS + _BLANK + r"[:?+]?=(?!=)" + _BLANK + _REST_OF_LINE,
    re.IGNORECASE,
)

#: The same idea for the separators `=` cannot cover: YAML's `NAME: value`,
#: the comma of `{"NAME": value}` / `setdefault("NAME", value)`, and the pipe
#: of a Markdown table row. These separate a name from ordinary prose as well
#: — "`NHL_ODDS_API_KEY`: the name of the GitHub secret" — so a match here is
#: a finding only if the value independently looks like a credential.
SEPARATED = re.compile(
    r"(?<![A-Za-z0-9])(" + _NAMES + r")" + _CLOSERS + _BLANK + r"[:,|]" + _BLANK + _REST_OF_LINE,
    re.IGNORECASE,
)

#: Does this token look like a credential VALUE rather than a word of prose?
#: One unbroken run of name-safe characters, twelve or longer, carrying a
#: digit, and not itself an identifier in shouting case. The length rejects
#: "the"; the class rejects a path ("docs/runbook-2024.md"); the digit rejects
#: "not-configured"; the shouting-case clause rejects a list of credential
#: NAMES. The two gaps this leaves — a letters-only value and a value with a
#: `.` or `/` — are pinned by `test_the_value_test_gaps_are_the_ones_documented`.
CREDENTIAL_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{11,}")
SHOUTING_CASE = re.compile(r"[A-Z0-9_]+")

#: Unicode categories that occupy no space and belong to no credential. `\S`
#: starts on U+200B and U+00AD, so they ride INTO a token rather than being
#: consumed as spacing; `_unwrap` deletes them by category, because a list of
#: codepoints is a spelling and the first codepoint not on it got through.
INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc"})


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    names = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    return [PROJECT_ROOT / name for name in names]


#: This file necessarily contains every pattern it hunts for, so it must not
#: scan its own body. Its NAME is scanned like every other tracked path.
SELF = Path(__file__).resolve()

#: Suffixes whose BODIES there is no point decoding. A file with one of these
#: suffixes still has a name, and a name needs no decoding.
BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"})


def _link_target(path: Path) -> str:
    """What a tracked symlink carries, which is neither name nor body.

    `git` stores a symlink as a blob whose contents are the target string, so
    `ln -s sk-live-… docs/provider_key` commits the credential in plaintext.
    `path.is_file()` is False for a dangling link, so the old body scan
    dropped it, and the name scan saw only `docs/provider_key`.
    """
    try:
        if not path.is_symlink():
            return ""
        return os.readlink(path)
    except OSError:
        return ""


def _is_this_file(path: Path) -> bool:
    """`Path.resolve()` raises on a symlink loop; a path that cannot be
    resolved is not this file and stays in the corpus."""
    try:
        return path.resolve() == SELF
    except (OSError, RuntimeError):
        return False


def _body_scannable(paths: Iterable[Path]) -> list[Path]:
    """The subset of `paths` whose contents are worth reading as text. A
    symlink is kept even when it dangles: its body reads as empty, and keeping
    it is what carries the path into the assignment scan."""
    keep: list[Path] = []
    for path in paths:
        if not path.is_file() and not path.is_symlink():
            continue
        if _is_this_file(path):
            continue
        if path.suffix in BINARY_SUFFIXES:
            continue
        keep.append(path)
    return keep


def _text_files() -> list[Path]:
    return _body_scannable(_tracked_files())


def _read(path: Path) -> str:
    """The file decoded as UTF-8, or `""` when it cannot be read at all."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _scannable(text: str) -> str:
    """`text` with every non-blank format and control character removed and
    Unicode compatibility forms folded onto their ASCII equivalents.

    Three attacks this closes, each written and observed to pass first:

    * a UTF-16 body decodes under `errors="ignore"` into `K\\x00E\\x00Y…`, and
      every matcher here wants an unbroken run — NUL is a control character
      and goes;
    * a U+200D ZERO WIDTH JOINER or a U+00AD SOFT HYPHEN inside
      `NHL_ODDS_API_KEY` left a name no pattern here recognised — not the
      assignment scan and not the drift guard either, so the leak was
      invisible twice over;
    * a fullwidth `＝` (U+FF1D) was not the operator, and fullwidth hex digits
      were not hex. NFKC folds them onto `=`, `:`, and the ASCII letters and
      digits.

    Whitespace is kept whatever its category — newline is a control character
    too, and stripping it turned every file into one line, which put the value
    on the line after `NAME=` beside the name and flagged `.env.example`.
    Found by running the rule over the tracked corpus, which is the only way a
    false positive is ever found.

    What this does NOT fold is a homoglyph from another script — Cyrillic `О`
    for Latin `O` — which is in the known-gaps ledger rather than claimed shut.
    """
    stripped = "".join(
        character
        for character in text
        if character.isspace() or unicodedata.category(character) not in INVISIBLE_CATEGORIES
    )
    return unicodedata.normalize("NFKC", stripped)


def _scan_text(path: Path) -> str:
    """Every body scan reads this, so there is one reading to keep correct."""
    return _scannable(_read(path))


def _hex_key_offenders(
    paths: Iterable[Path],
    allowed: set[str],
    root: Path,
    *,
    names: bool = True,
    bodies: bool = True,
) -> list[str]:
    """Every 32-hex run in `paths` — name, symlink target, or body — that is
    not a recorded value spent under `EXEMPT_SCOPE`. Six characters of each
    finding are reported: enough to locate, not enough to publish."""
    offenders: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        permitted = allowed if relative.startswith(EXEMPT_SCOPE) else set()
        found: list[str] = []
        if names:
            found += [match.group(0) for match in HEX_KEY.finditer(relative)]
            found += [match.group(0) for match in HEX_KEY.finditer(_link_target(path))]
        if bodies:
            found += [match.group(0) for match in HEX_KEY.finditer(_scan_text(path))]
        for value in found:
            if value in permitted:
                continue
            finding = f"{relative}: {value[:6]}..."
            if finding not in offenders:
                offenders.append(finding)
    return offenders


def _hex_offenders_for_corpus(tracked: Iterable[Path], allowed: set[str], root: Path) -> list[str]:
    """Names over the whole corpus, bodies over the part that has one worth
    reading. The split is what a `.png` suffix used to walk past entirely."""
    paths = list(tracked)
    offenders = _hex_key_offenders(paths, allowed, root, bodies=False)
    offenders += _hex_key_offenders(_body_scannable(paths), allowed, root, names=False)
    return offenders


def _unwrap(raw: str) -> str:
    """Strip the punctuation that surrounds a value in source and prose:
    invisible characters first (by category), then a string-literal prefix,
    quotes, closers, quotes again, and the leading `-` of a shell default."""
    visible = "".join(
        character for character in raw if unicodedata.category(character) not in INVISIBLE_CATEGORIES
    )
    without_prefix = re.sub(r"^[fFrRbBuU]{1,2}(?=[\"'])", "", visible)
    return without_prefix.strip("'\"`").strip(",;)}]").strip("'\"`").lstrip("-")


def _unbracket(value: str) -> str:
    return value.strip("<>{} ")


def _looks_like_a_credential_value(value: str) -> bool:
    if not CREDENTIAL_VALUE.fullmatch(value):
        return False
    if SHOUTING_CASE.fullmatch(value):
        return False
    return any(character.isdigit() for character in value)


def _is_a_reference(value: str) -> bool:
    """`$VAR`, `<placeholder>`, `${{ secrets.X }}`, an f-string `{SECRET}`.

    `$` is unconditional. The bracket forms are NOT: anything beginning `<` or
    `{` used to be waved through, so `NAME: <sk-live-…>` — the leak wearing
    the placeholder's clothes — passed. The brackets come off and what is
    inside has to fail the value test.
    """
    if value[0] == "$":
        return True
    if value[0] in "<{":
        return not _looks_like_a_credential_value(_unbracket(value))
    return False


def _assignment_offenders(paths: Iterable[Path], root: Path) -> list[str]:
    """Every `CREDENTIAL_NAME <given> <real value>` in `paths`, by file and
    name. The value itself is never reported.

    Every whitespace-separated token on the rest of the line is evaluated,
    and an empty token advances rather than ending the line — reading one
    token and giving up is what let `os.environ["NAME"] = "" "<key>"` and the
    third cell of a Markdown table row pass. For the `=` family the first
    non-empty token needs no value test (nothing writes `NAME=` in prose);
    every later token, and every token under `:`/`,`/`|`, has to look like a
    credential value, which is what keeps the sentence after
    `export NAME=<placeholder>` from being a finding.
    """
    offenders: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text = _scan_text(path)
        target = _link_target(path)
        if target:
            text = f"{text}\n{target}\n{_scannable(target)}"
        for pattern, value_must_look_real in ((ASSIGNMENT, False), (SEPARATED, True)):
            for match in pattern.finditer(text):
                tokens = [
                    unwrapped
                    for unwrapped in (_unwrap(token) for token in match.group(2).split())
                    if unwrapped
                ]
                for index, value in enumerate(tokens):
                    must_look_real = value_must_look_real or index > 0
                    if value in PLACEHOLDERS:
                        continue
                    if not any(character.isalnum() for character in value):
                        # `"NAME=" + "…"` leaves `+` as the first token. No
                        # provider issues a credential with no letter or digit
                        # in it, so bare punctuation is an operator, not a
                        # value. Found on this repository's own tests.
                        continue
                    if _is_a_reference(value):
                        continue
                    if must_look_real and not _looks_like_a_credential_value(_unbracket(value)):
                        continue
                    finding = f"{relative}: {match.group(1)}"
                    if finding not in offenders:
                        offenders.append(finding)
                    break
    return offenders


# --------------------------------------------------------------------------
# The rules, applied to the real repository.
# --------------------------------------------------------------------------


def test_env_file_is_never_tracked() -> None:
    tracked = {path.name for path in _tracked_files()}

    assert ENV_FILENAME not in tracked


def test_env_file_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ENV_FILENAME], cwd=PROJECT_ROOT, capture_output=True
    )

    assert result.returncode == 0, ".env must stay gitignored"


def test_the_corpus_is_not_empty() -> None:
    """Every scan below is a loop over `git ls-files`. An empty list — a
    scan run outside the repository, or a broken git — would pass every one
    of them by having read nothing. Absence is never a pass."""
    tracked = _tracked_files()

    assert len(tracked) > 50, len(tracked)
    assert len(_text_files()) > 50


def test_no_tracked_file_assigns_a_real_credential() -> None:
    """`<a credential name>=<something real>` must not appear in a tracked
    file. Every tracked text file, every suffix: Markdown is not a safer place
    to write a key than Python is."""
    offenders = _assignment_offenders(_text_files(), PROJECT_ROOT)

    assert offenders == [], f"credential assignment in tracked files: {offenders}"


def test_no_credential_name_in_the_repository_is_unknown_to_this_guard() -> None:
    """A credential name this module has not been taught is a name it cannot
    catch being assigned."""
    found: set[str] = set()
    for path in _text_files():
        found.update(CREDENTIAL_NAME_SHAPE.findall(_scan_text(path)))

    assert found, "no credential name found in any tracked file — scan is broken"
    assert found <= set(CREDENTIAL_NAMES), (
        f"credential names this guard cannot recognise: {sorted(found - set(CREDENTIAL_NAMES))}"
    )


def test_no_tracked_file_contains_an_odds_api_key_shape() -> None:
    """Every tracked file by NAME, every tracked symlink by TARGET, every
    tracked text file by BODY. No file is exempt from any scan for what it is
    called — only for what it is, and only from the scan that cannot apply."""
    offenders = _hex_offenders_for_corpus(_tracked_files(), _exempt_hex_values(), PROJECT_ROOT)

    assert offenders == [], f"possible credential in tracked files: {offenders}"


def test_generated_reports_never_include_the_api_key_parameter() -> None:
    offenders: list[str] = []
    for path in _text_files():
        for match in API_KEY_PARAM.finditer(_scan_text(path)):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)[:10]}...")

    assert offenders == [], f"apiKey= with a value in tracked files: {offenders}"


def test_data_outputs_reports_are_not_tracked_with_secrets() -> None:
    """Report artifacts under data/outputs must be clean if tracked at all —
    by name as well as by body, through the one matcher and one spend rule."""
    known = _exempt_hex_values()
    named = [
        path
        for path in _tracked_files()
        if path.relative_to(PROJECT_ROOT).as_posix().startswith("data/outputs/")
    ]
    reports = _body_scannable(named)
    offenders = _hex_key_offenders(named, known, PROJECT_ROOT, bodies=False)
    offenders += _hex_key_offenders(reports, known, PROJECT_ROOT, names=False)
    offenders += [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}: apiKey="
        for path in reports
        if API_KEY_PARAM.search(_scan_text(path))
    ]

    assert named, "no tracked report under data/outputs/ — the scan ran over nothing"
    assert offenders == [], f"tracked report contains a credential: {offenders}"


def test_every_cached_response_filename_is_corroborated() -> None:
    """A cached response is named after the event it holds, so stem and body
    must agree. `.gitignore` makes `data/raw/` untrackable, so on the real
    repository both sets are empty; the synthetic half of this rule is in
    `test_a_hex_run_that_exists_only_in_a_filename_is_still_a_finding`."""
    content_ids, name_ids = _collect_event_ids(_tracked_files(), PROJECT_ROOT)
    uncorroborated = sorted(stem[:6] + "..." for stem in name_ids - content_ids)

    assert uncorroborated == [], f"cached-response filenames no body records: {uncorroborated}"


# --------------------------------------------------------------------------
# Positive controls: each matcher fires on the real thing.
# --------------------------------------------------------------------------


def test_the_api_key_parameter_check_still_catches_a_real_leak() -> None:
    assert API_KEY_PARAM.search("https://x/v4/odds?apiKey=0123456789abcdef&r=us")
    assert API_KEY_PARAM.search("apiKey=abcdef0123456789abcdef0123456789")
    assert API_KEY_PARAM.search("apiKey=sk-live-4f19c0d27ba6e83d")
    for spelling in ("apikey=", "API_KEY=", "api-key=", "ApiKey="):
        assert API_KEY_PARAM.search(f"https://x/v4/odds?{spelling}aZ90bYx8cW7v"), spelling
    # ...and stays quiet on the defences that mention the token.
    assert not API_KEY_PARAM.search('re.compile(r"(apiKey=)[^&s]+")')
    assert not API_KEY_PARAM.search('assert "apiKey=" not in text')
    assert not API_KEY_PARAM.search("apiKey=[redacted]")


def test_the_key_shape_check_still_catches_a_real_leak() -> None:
    assert HEX_KEY.search("key is 0123456789abcdef0123456789abcdef here")
    assert not HEX_KEY.search("sha256 " + "a" * 64)
    assert not HEX_KEY.search("docs/" + "a" * 40 + ".txt")


def test_the_key_shape_matcher_is_not_stopped_by_a_word_character() -> None:
    """One matcher, and it sees the cache naming convention wherever it is
    read — a path, a body, an identifier."""
    key = "0123456789abcdef0123456789abcdef"
    for fence in ("_", "-", ".", "/", "x", ""):
        assert HEX_KEY.search(f"{fence}{key}{fence}"), fence
    assert HEX_KEY.search(f"data/raw/{key}_odds.json")
    assert HEX_KEY.search(f'CACHE = f"{key}_odds.json"')
    assert HEX_KEY.search(f"KEY_{key} = 1")
    assert HEX_KEY.search(key.upper())


@pytest.mark.parametrize("name", CREDENTIAL_NAMES)
def test_credential_names_are_referenced_but_never_valued(name: str) -> None:
    assert isinstance(name, str) and name
    assert CREDENTIAL_NAME_SHAPE.fullmatch(name), name


def test_the_production_credential_name_is_the_one_the_workflow_uses() -> None:
    assert GITHUB_SECRET_NAME in PROVIDER_ENV_ALLOWLIST
    assert GITHUB_SECRET_NAME in CREDENTIAL_NAMES
    assert "NHL_ODDS_API_BASE_URL" not in CREDENTIAL_NAMES


def test_the_credential_name_shape_knows_more_than_one_spelling() -> None:
    for spelling in ("NHL_ODDS_APIKEY", "NHL_ODDS_API_TOKEN", "X_API_KEY"):
        assert CREDENTIAL_NAME_SHAPE.findall(f"export {spelling}=x") == [spelling]
    assert CREDENTIAL_NAME_SHAPE.findall("PROJECT_ROOT = Path(__file__)") == []
    assert CREDENTIAL_NAME_SHAPE.findall("API_KEY_PARAM = re.compile(...)") == []


def test_the_guard_excludes_itself_from_its_own_scan() -> None:
    scanned = {path.resolve() for path in _text_files()}

    assert SELF not in scanned


def test_the_guard_still_scans_other_test_files() -> None:
    scanned = {path.name for path in _text_files()}

    assert "test_config.py" in scanned
    assert "test_provider_env_file.py" in scanned
    assert "test_workflows.py" in scanned


# --------------------------------------------------------------------------
# Reproductions: each of the audit's five bypasses, run against this code.
# --------------------------------------------------------------------------


def test_a_file_is_never_exempt_from_the_hex_scan_for_what_it_is_called(tmp_path: Path) -> None:
    """Reproduction (a): the by-name skip of "checksum" and "receipt" files.

    Identical bytes passed as `week3_acceptance_receipt.md` and failed as
    `week3_acceptance.md`. The receipts directory is the one this lab keeps
    human approvals in — the blind spot sat on the files most likely to carry
    provenance. Fails against the old `test_no_tracked_file_contains_an_odds_
    api_key_shape`, which `continue`d past both names.
    """
    key = "0123456789abcdef0123456789abcdef"
    receipts = tmp_path / "data" / "manual" / "human_acceptance_receipts"
    receipts.mkdir(parents=True)
    for name in ("odds_api-20260827-receipt.json", "manifest_checksum.txt"):
        (receipts / name).write_text(f'{{"note": "recorded against {key}"}}\n', encoding="utf-8")

    found = _hex_key_offenders(sorted(receipts.iterdir()), set(), tmp_path)

    assert found == [
        f"data/manual/human_acceptance_receipts/manifest_checksum.txt: {key[:6]}...",
        f"data/manual/human_acceptance_receipts/odds_api-20260827-receipt.json: {key[:6]}...",
    ]
    # ...and a SHA-256 in a checksum file never needed the skip: the
    # lookarounds refuse to fire inside 64 hex characters.
    digest = tmp_path / "SHA256SUMS"
    digest.write_text("a" * 64 + "  data/outputs/report.md\n", encoding="utf-8")

    assert _hex_key_offenders([digest], set(), tmp_path) == []


def test_a_hex_key_beside_an_underscore_or_uppercased_is_a_finding(tmp_path: Path) -> None:
    """Reproduction (b): `\\b[0-9a-f]{32}\\b`.

    `_` is a word character, so the boundary never opened beside it, and the
    class was lowercase-only. Each body below carried a real credential past a
    green suite. Several spellings on purpose: a fix that catches only the
    first is a narrower guard, not a repaired one.
    """
    key = "0123456789abcdef0123456789abcdef"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    spellings = {
        "cache.py": f'CACHE = f"{key}_odds.json"\n',
        "named.py": f"KEY_{key} = 1\n",
        "fenced.py": f"_{key}_\n",
        "url.md": f"https://api.example/v4/{key}/odds\n",
        "ident.py": f"ODDS{key}ZONE = 2\n",
        "upper.py": f'KEY = "{key.upper()}"\n',
        "mixed.py": f'KEY = "{key[:16].upper()}{key[16:]}"\n',
    }
    for name, body in spellings.items():
        (scripts / name).write_text(body, encoding="utf-8")

    offenders = _hex_key_offenders([scripts / name for name in sorted(spellings)], set(), tmp_path)

    assert [offender.split(":")[0] for offender in offenders] == [
        f"scripts/{name}" for name in sorted(spellings)
    ]
    digests = tmp_path / "SHA256SUMS"
    digests.write_text("\n".join(f"{letter * 64}  r{i}.md" for i, letter in enumerate("abcdef")), encoding="utf-8")

    assert _hex_key_offenders([digests], set(), tmp_path) == []


def test_a_hex_run_in_a_filename_or_a_symlink_target_is_a_finding(tmp_path: Path) -> None:
    """Reproduction (c): only bodies were scanned, and only after `is_file()`.

    A key in a filename needed no decoding and was read by nothing; a tracked
    `docs/<key>.png` was read by nothing twice over, because the name scan sat
    behind the filter that drops binaries from the BODY scan; and a symlink
    whose target was the key was dropped on `is_file()` — False for a dangling
    link — so neither its target nor its body was ever read.
    """
    key = "0123456789abcdef0123456789abcdef"
    name = GITHUB_SECRET_NAME
    value = "sk-live-4f19c0d27ba6e83d"
    docs = tmp_path / "docs"
    docs.mkdir()
    plain = docs / f"{key}.md"
    plain.write_text("Notes on the fetch. Nothing sensitive in here.\n", encoding="utf-8")
    cache_shaped = docs / f"{key}_odds.json"
    cache_shaped.write_text(json.dumps({"ok": True}), encoding="utf-8")
    binaries = [f"{key}.png", f"cover-{key}.jpg", f"{key}_chart.zip"]
    for binary in binaries:
        (docs / binary).write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01")
    hex_link = docs / "provider_key"
    hex_link.symlink_to(key)
    assignment_link = docs / "note"
    assignment_link.symlink_to(f"{name}={value}")

    assert not hex_link.is_file()
    assert _body_scannable([docs / binary for binary in binaries]) == []
    corpus = [plain, cache_shaped, *(docs / binary for binary in binaries), hex_link]

    assert _hex_offenders_for_corpus(corpus, set(), tmp_path) == [
        f"docs/{key}.md: {key[:6]}...",
        f"docs/{key}_odds.json: {key[:6]}...",
        *[f"docs/{binary}: {key[:6]}..." for binary in binaries],
        f"docs/provider_key: {key[:6]}...",
    ]
    assert _body_scannable([assignment_link]) == [assignment_link]
    assert _read(assignment_link) == ""
    assert _assignment_offenders([assignment_link], tmp_path) == [f"docs/note: {name}"]

    # ...a symlink loop is a finding-free file, not a crash.
    loop = docs / "loop"
    loop.symlink_to("loop")

    assert _hex_offenders_for_corpus([loop], set(), tmp_path) == []
    assert _assignment_offenders([loop], tmp_path) == []

    # ...and a genuine cached response, named after the event its body
    # records, stays green: the stem is a recorded value spent in scope.
    recorded = "a1b2c3d4" * 4
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    cached = raw / f"{recorded}_odds.json"
    cached.write_text(json.dumps({"id": recorded, "bookmakers": []}), encoding="utf-8")
    content_ids, _ = _collect_event_ids([cached], tmp_path)

    assert content_ids == {recorded}
    assert _hex_offenders_for_corpus([cached], content_ids, tmp_path) == []


def test_a_decoy_filename_cannot_nominate_an_exemption(tmp_path: Path) -> None:
    """Reproduction (d): self-nomination.

    The stem harvest ran over EVERY tracked file before any directory
    restriction, so a decoy `<key>_x.md` at the repository root put the key
    into the exemption set, and `scripts/fetch.py` carrying the same key was
    green. Measured on exactly this corpus before the fix: zero offenders.
    Now the root decoy nominates nothing, a report under `data/outputs/`
    nominates nothing either, and only the provider's own cache can.
    """
    key = "0123456789abcdef0123456789abcdef"
    decoy = tmp_path / f"{key}_x.md"
    decoy.write_text("nothing here\n", encoding="utf-8")
    outputs = tmp_path / "data" / "outputs"
    outputs.mkdir(parents=True)
    report = outputs / "retention_probe.json"
    report.write_text(json.dumps({"id": key}), encoding="utf-8")
    table = outputs / "bought_prices.csv"
    table.write_text(f"event_id,price\n{key},-110\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    hardcoded = scripts / "fetch.py"
    hardcoded.write_text(f'API_KEY = "{key}"\n', encoding="utf-8")

    corpus = [decoy, report, table, hardcoded]
    content_ids, name_ids = _collect_event_ids(corpus, tmp_path)

    assert (content_ids, name_ids) == (set(), set())
    assert _hex_offenders_for_corpus(corpus, content_ids, tmp_path) == [
        f"{key}_x.md: {key[:6]}...",
        f"data/outputs/retention_probe.json: {key[:6]}...",
        f"data/outputs/bought_prices.csv: {key[:6]}...",
        f"scripts/fetch.py: {key[:6]}...",
    ]

    # ...and an exemption the cache genuinely earns is spendable under
    # `EXEMPT_SCOPE` and nowhere else.
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    cached = raw / f"{key}_odds.json"
    cached.write_text(json.dumps({"events": [{"id": key}]}), encoding="utf-8")
    content_ids, name_ids = _collect_event_ids([cached, report, hardcoded], tmp_path)

    assert content_ids == {key} and name_ids == {key}
    assert _hex_offenders_for_corpus([cached, report, hardcoded], content_ids, tmp_path) == [
        f"scripts/fetch.py: {key[:6]}..."
    ]


def test_a_hex_run_that_exists_only_in_a_filename_is_still_a_finding(tmp_path: Path) -> None:
    """A filename is a claim about what a file holds, not evidence of it.
    A stem no body corroborates is reported directly, inside the cache too."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    key = "0123456789abcdef0123456789abcdef"
    empty = raw / f"{key}_odds.json"
    empty.write_text(json.dumps({"ok": True}), encoding="utf-8")

    content_ids, name_ids = _collect_event_ids([empty], tmp_path)

    assert key not in content_ids
    assert name_ids - content_ids == {key}
    assert _hex_key_offenders([empty], content_ids, tmp_path) == [
        f"data/raw/{key}_odds.json: {key[:6]}..."
    ]


def test_the_event_id_exemption_is_by_value_and_not_by_directory(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    recorded = "a1b2c3d4" * 4
    invented = "deadbeef" * 4
    cached = raw / f"{recorded}_odds.json"
    cached.write_text(json.dumps({"id": recorded, "bookmakers": []}), encoding="utf-8")
    neighbour = raw / "settings.json"
    neighbour.write_text(json.dumps({"note": invented}), encoding="utf-8")

    content_ids, _ = _collect_event_ids([cached, neighbour], tmp_path)

    assert content_ids == {recorded}
    assert _hex_key_offenders([cached, neighbour], content_ids, tmp_path) == [
        f"data/raw/settings.json: {invented[:6]}..."
    ]


def test_the_canonical_python_assignment_and_yaml_are_findings(tmp_path: Path) -> None:
    """Reproduction (e): `ASSIGNMENT` knew `NAME=value` only.

    `os.environ["NAME"] = "<key>"` — a closing quote and bracket between the
    name and the `=` — was not a finding in a `.py`, a `.md` or a `.yml`, and
    neither was YAML's `NAME: <key>`. Every file below carried the same value
    verbatim past a green suite.
    """
    name = GITHUB_SECRET_NAME
    value = "sk-live-4f19c0d27ba6e83d"
    leaks = {
        "src/fetch.py": f'import os\nos.environ["{name}"] = "{value}"\n',
        "docs/runbook.md": f'Then run `os.environ["{name}"] = "{value}"`.\n',
        "ci/gameday.yml": f"env:\n  {name}: {value}\n",
    }
    written: list[Path] = []
    for relative, body in leaks.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(path)

    assert _assignment_offenders(written, tmp_path) == [
        f"src/fetch.py: {name}",
        f"docs/runbook.md: {name}",
        f"ci/gameday.yml: {name}",
    ]


def test_a_credential_committed_in_markdown_is_a_finding(tmp_path: Path) -> None:
    """Reproduction (e), the documentation half: `.md`, `.rst` and `.txt`
    were exempt from the assignment scan unless the value was 32 hex
    characters, and a leaked key is rarely 32 hex characters."""
    name = GITHUB_SECRET_NAME
    docs = tmp_path / "docs"
    docs.mkdir()
    for suffix in ("md", "rst", "txt"):
        (docs / f"runbook.{suffix}").write_text(
            f"Export the credential before the fetch:\n\n    export {name}=" + "sk-live-4f19c0d27ba6e83d\n",
            encoding="utf-8",
        )

    assert _assignment_offenders(sorted(docs.iterdir()), tmp_path) == [
        f"docs/runbook.{suffix}: {name}" for suffix in ("md", "rst", "txt")
    ]

    fine = docs / "setup.md"
    fine.write_text(
        f"Run `export {name}=your-api-key`, or in CI set\n"
        f"`{name}=" + "${{ secrets." + name + " }}`, or locally\n"
        f"`{name}=$ODDS_KEY` / `{name}=<paste yours>`.\n",
        encoding="utf-8",
    )

    assert _assignment_offenders([fine], tmp_path) == []


def test_the_assignment_scan_survives_a_rewording(tmp_path: Path) -> None:
    """The attacks tried against the fix, and the prose it must not eat."""
    name = GITHUB_SECRET_NAME
    value = "sk-live-4f19c0d27ba6e83d"
    hexish = "aB3xQ9zLmN2pR7tV"
    rewordings = {
        "a.py": f'os.environ["{name}"] = "{value}"',
        "b.py": f"os.environ['{name}']='{value}'",
        "c.py": f'os.environ.setdefault("{name}", "{value}")',
        "d.py": f'CONFIG = {{"{name}": "{value}"}}',
        "e.py": f'settings["env"]["{name}"] = "{hexish}"',
        "f.yml": f"  {name}: {value}",
        "g.yml": f'  {name}: "{value}"',
        "h.md": f"- `{name}` = {value}",
        "i.sh": f': "${{{name}:-{value}}}"',
        "j.json": f'{{"{name}": "{hexish}"}}',
        "k.py": f'os.environ[ "{name}" ] = "{value}"',
        "l.toml": f'{name} = "{value}"',
        "m.mk": f"{name} := {value}",
        "n.mk": f"{name} ?= {value}",
        "o.sh": f"{name} += {value}",
        "p.sh": f': "${{{name}:={value}}}"',
        "q.md": f"**{name}**: {value}",
        "r.md": f"<code>{name}</code>: {value}",
        "s.md": f"_{name}_: {value}",
        "t.md": f"| `{name}` | live | {value} |",
        "u.py": f'os.environ["{name}"] = "" "{value}"',
        "v.py": f'os.environ["{name.lower()}"] = "{value}"',
        "w.yml": f"{name}: <{value}>",
        "x.sh": f"export {name}= {value}",
        "y.sh": f"export {name} = {value}",
        "z.yml": f"{name}:\u200b{value}",
    }
    for filename, body in rewordings.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")

    caught = _assignment_offenders([tmp_path / filename for filename in sorted(rewordings)], tmp_path)

    assert [finding.split(":")[0] for finding in caught] == sorted(rewordings)

    prose = {
        "table.md": f"| `{name}` | The name of the GitHub secret holding the provider credential |",
        "gloss.md": f"`{name}`: the name of the GitHub secret",
        "list.py": f'CREDENTIAL_NAMES = frozenset({{"{name}", "NHL_ODDS_API_BASE_URL"}})',
        "guard.sh": f'if [ -n "${{{name}:-}}" ]; then echo missing; fi',
        "ci.yml": f"  {name}: ${{{{ secrets.{name} }}}}",
        "empty.yml": f'  {name}: ""',
        "state.md": f"{name}: not-configured",
        "where.md": f"{name}: see docs/runbook-2024.md",
        "ref.md": f"{name}: $ODDS_KEY",
        "shape.md": f"Run `export {name}=your-api-key` first.",
        "example.env": f"{name}=",
        "next_line.env": f"{name}=\n{value}",
        "fstring.py": f'os.environ["{name}"] = f"{{SECRET}}"',
        "sibling.yml": f"{name}_FILE: {value}",
        "placeholder.md": f"{name}=<paste yours>",
        "keyword.py": f'raises(MissingCredentialError, match="{name}")',
        "equality.py": f'assert environment["{name}"] == SECRET',
        "inequality.py": f"assert {name} != {value}",
        "compare.py": f"assert {name} >= {value}",
        "concat.py": f'_write_env(tmp_path, "{name}=" + "   ")',
    }
    for filename, body in prose.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")

    assert _assignment_offenders([tmp_path / filename for filename in sorted(prose)], tmp_path) == []


def test_an_invisible_or_fullwidth_character_inside_the_name_is_a_finding(
    tmp_path: Path,
) -> None:
    """Attack on the NAME rather than the value, found after the value-side
    rules were written. A zero-width joiner or a soft hyphen inside
    `NHL_ODDS_API_KEY` left a name nothing here recognised — the assignment
    scan and the drift guard both read the same broken token — and a fullwidth
    `＝` was not an operator. All three were run and observed to pass before
    `_scannable` existed. The drift guard is asserted alongside, because a
    name it cannot see is a name it cannot demand be taught."""
    name = GITHUB_SECRET_NAME
    value = "sk-live-4f19c0d27ba6e83d"
    joined = name[:8] + "\u200d" + name[8:]
    hyphenated = name[:12] + "\u00ad" + name[12:]
    cases = {
        "zwj.md": f"{joined}={value}",
        "soft_hyphen.py": f'os.environ["{hyphenated}"] = "{value}"',
        "fullwidth.md": f"{name}\uff1d{value}",
        "fullwidth_colon.yml": f"{name}\uff1a {value}",
        "fullwidth_hex.py": "KEY = " + "".join(chr(ord(c) + 0xFEE0) for c in "0123456789abcdef" * 2),
    }
    for filename, body in cases.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    paths = [tmp_path / filename for filename in sorted(cases)]

    assert [finding.split(":")[0] for finding in _assignment_offenders(paths, tmp_path)] == [
        "fullwidth.md", "fullwidth_colon.yml", "soft_hyphen.py", "zwj.md",
    ]
    assert _hex_key_offenders(paths, set(), tmp_path) == ["fullwidth_hex.py: 012345..."]
    for path in paths:
        if path.name != "fullwidth_hex.py":
            assert CREDENTIAL_NAME_SHAPE.findall(_scan_text(path)) == [name], path.name


def test_a_credential_in_a_utf16_body_is_a_finding(tmp_path: Path) -> None:
    key = "0123456789abcdef0123456789abcdef"
    name = GITHUB_SECRET_NAME
    little = tmp_path / "notes.txt"
    little.write_bytes(f'KEY = "{key}"\n'.encode("utf-16-le"))
    big = tmp_path / "config.txt"
    big.write_bytes(f'{name} = "sk-live-4f19c0d27ba6e83d"\n'.encode("utf-16-be"))

    assert "\x00" in little.read_text(encoding="utf-8", errors="ignore")
    assert _hex_key_offenders([little], set(), tmp_path) == [f"notes.txt: {key[:6]}..."]
    assert _assignment_offenders([big], tmp_path) == [f"config.txt: {name}"]


def test_the_value_test_gaps_are_the_ones_documented() -> None:
    assert not _looks_like_a_credential_value("purelettersecret")
    assert not _looks_like_a_credential_value("ab12.cd34.ef56")
    assert not _looks_like_a_credential_value("sk/live/4f19c0d2")
    assert ASSIGNMENT.search(f"{GITHUB_SECRET_NAME}=purelettersecret")
    assert ASSIGNMENT.search(f"{GITHUB_SECRET_NAME}=ab12.cd34.ef56")
    assert not _looks_like_a_credential_value("the")
    assert not _looks_like_a_credential_value("NHL_ODDS_API_KEY")
    assert not _looks_like_a_credential_value("not-configured")
    assert _looks_like_a_credential_value("sk-live-4f19c0d27ba6e83d")
    assert _looks_like_a_credential_value("0123456789abcdef0123456789abcdef")


def test_the_gaps_this_guard_still_has_are_the_ones_written_down(tmp_path: Path) -> None:
    """The rewordings that still get past this module, asserted not remembered.

    Each line below is an attack that was written, run, and observed to pass.
    **This asserts nothing is allowed** — every gate above still demands an
    empty offender list. It is a ledger of coverage, and the correct response
    to any line is to close it and delete the line; a failure here means
    someone closed a gap, which is good news.

    * Hex glued to another hex character (`<key>00`, `ODDS<key>CACHE`): a run
      longer than 32, and the refusal to fire inside one is what keeps a
      SHA-256 quiet.
    * A key split across a concatenation. Nothing here parses source.
    * A value on the line after its name. Newline is not a blank on purpose;
      `\\s` would read `.env.example`'s empty `NAME=` plus the next line.
    * A name assembled at runtime from pieces.
    * A separator this module does not know: a tab, a prose arrow.
    * A value under `:`/`,`/`|` shorter than twelve characters, all letters,
      or carrying `.` or `/` — the value test's edges, and the price of
      letting ordinary prose through. The `=` family runs no value test on
      its FIRST token and so has none of these gaps there.
    * A literal nested inside a `$` expansion: `${NAME:=${OTHER:-<key>}}`.
    * A value more than 512 characters along the line, or more than eight
      characters of markup between the name and the operator.
    * Markup carrying alphanumerics that is not an HTML tag — a Markdown link
      `[NAME](#anchor): <key>` — and an HTML entity `NAME&nbsp;= <key>`.
    * An invisible character Unicode files as a LETTER — U+3164 HANGUL
      FILLER, category Lo — glued to the front of a value under `:`. Neither
      `_BLANK` (not whitespace) nor `INVISIBLE_CATEGORIES` (not Cf/Cc) removes
      it, so the value fails the digit-and-length test. The `=` family catches
      it, having no value test on the first token; both halves are run below.
    * An encoded body — base64 or otherwise. Nothing here decodes. (UTF-16 IS
      covered: that was a decoding this module was getting wrong.)
    * A homoglyph inside the NAME — Cyrillic `О` (U+041E) for Latin `O` in
      `NHL_ODDS_API_KEY`. NFKC does not fold across scripts, so neither the
      assignment scan nor the drift guard sees the name. An invisible or a
      fullwidth character inside the name IS caught, by `_scannable`.
    * A key in a commit message, a branch name or a tag. Those are history,
      not tracked files, and `git ls-files` is the corpus here.
    * A text body wearing a binary suffix: `notes.pdf` full of ASCII is not
      body-scanned. Its NAME is. A symlink wearing a binary suffix is the
      same trade: hex-scanned by name and target, dropped from the assignment
      scan.
    * This file's own body.
    """
    name = GITHUB_SECRET_NAME
    value = "sk-live-4f19c0d27ba6e83d"
    key = "0123456789abcdef0123456789abcdef"
    gaps = {
        "padded.py": f'KEY = "{key}00"',
        "glued.py": f"ODDS{key}CACHE = 2",
        "split.py": f'KEY = "{key[:16]}" "{key[16:]}"',
        "block.yml": f"{name}: >\n  {value}",
        "next_line.env": f"{name}=\n{value}",
        "built.py": f'os.environ["NHL_ODDS_" "API_KEY"] = "{value}"',
        "arrow.md": f"{name} -> {value}",
        "column.tsv": f"{name}\t{value}",
        "short.yml": f"{name}: abc123def45",
        "encoded.py": 'KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="',
        "closers.md": f"{name}]]]]]]]]]]: {value}",
        "link.md": f"[{name}](#the-secret): {value}",
        "entity.md": f"{name}&nbsp;= {value}",
        "filler.md": f"{name}:\u3164{value}",
        "past_colon.md": f"{name}: <your-key> sk.live.4f19c0d27ba6e83d",
        "far.md": f"{name}: " + "prose " * 120 + value,
        "nested.sh": ': "${' + name + ':=${OTHER:-' + value + '}}"',
        "homoglyph.md": f"{name.replace('O', chr(0x041E))}={value}",
    }
    for filename, body in gaps.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")
    paths = [tmp_path / filename for filename in sorted(gaps)]

    assert _hex_key_offenders(paths, set(), tmp_path) == []
    assert _assignment_offenders(paths, tmp_path) == []

    disguised = tmp_path / "notes.pdf"
    disguised.write_text(f'KEY = "{key}"\n{name} = "{value}"\n', encoding="utf-8")
    assert _body_scannable([disguised]) == []
    assert _hex_offenders_for_corpus([disguised], set(), tmp_path) == []
    named = tmp_path / f"{key}.pdf"
    named.write_bytes(b"%PDF-1.4\n")
    assert _hex_offenders_for_corpus([named], set(), tmp_path) == [f"{key}.pdf: {key[:6]}..."]
    cover = tmp_path / "cover.png"
    cover.symlink_to(f"{name}={value}")
    assert _assignment_offenders(_body_scannable([cover]), tmp_path) == []

    # ...and the halves of those gaps that are NOT open, so narrowing one back
    # fails here rather than passing quietly.
    caught = {
        "filler_equals.md": f"{name}=\u3164{value}",
        "past_equals_real.sh": f"{name}=$UNUSED {value}",
        "eight_closers.md": f"{name}]]]]]]]]: {value}",
        "bracketed.yml": f"{name}: <{value}>",
    }
    for filename, body in caught.items():
        (tmp_path / filename).write_text(body + "\n", encoding="utf-8")

    assert _assignment_offenders([tmp_path / filename for filename in sorted(caught)], tmp_path) == [
        f"{filename}: {name}" for filename in sorted(caught)
    ]
