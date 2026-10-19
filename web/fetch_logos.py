"""Fetch one logo per NHL team into web/logos/<ABBR>.png for the site's team circles.

The Board, Results and Graphic pages show `teams[abbr].logo` from board.json, falling back to
`./logos/<ABBR>.png` and then to the coloured abbreviation. `web/build_site_json.py` writes the key
only for a file that exists here, so this script is what fills the folder. It is run by hand, once,
and the PNGs are committed; no workflow runs it.

Standard library only. It reads no credential, spends no provider credit, and is idempotent: a team
whose file already exists is skipped, never fetched again.

Source order per team, the first that answers 200 with a real PNG (signature, IHDR, every chunk's CRC,
IEND, an IDAT stream that inflates, 500 px on a side, more than 2 KB):

1. ESPN, the host the live scoreboard already reads: each team's `logos[0].href` straight off
   `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams`, mapped to the board's abbreviation
   through `ESPN_TO_BOARD` in web/lib/live.js and the builder's `TEAMS` (by name when the code misses).
   ESPN is asked with urllib's default User-Agent: measured 2026-10-18, it answered a descriptive agent
   with 403 Forbidden and the default with 200.
2. The Wikimedia Commons API, only for a team ESPN lacks, with a descriptive User-Agent that names a
   contact (Wikimedia's policy), backing off on 429: the first SVG/PNG result's 500-px thumbnail.
3. Nothing. The file is not written and the page shows the abbreviation.

Every file is listed with the URL it came from in web/logos/SOURCES.md. The logos are the league's and
the clubs' trademarks, shown for identification only.

    python web/fetch_logos.py              # fill web/logos/, skipping files that exist
    python web/fetch_logos.py --dest DIR   # somewhere else
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import struct
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

WEB = Path(__file__).resolve().parent
LOGOS = WEB / "logos"
LIVE_JS = WEB / "lib" / "live.js"
BUILDER = WEB / "build_site_json.py"

ESPN_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
#: Wikimedia asks every automated client to identify itself with a way to reach its operator.
COMMONS_AGENT = "nhl-betting-lab-fetch-logos/1.0 (https://github.com/cooperross399/nhl-betting-lab; team logos for the site)"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_BYTES = 2048
SIZE_PX = 500
TIMEOUT = 30
#: The longest a Retry-After is obeyed for; past it the source is given up on for this team.
MAX_WAIT = 60.0
NOTICE = ("The logos are the National Hockey League's and its clubs' trademarks, shown for identification only. "
          "Nothing here claims or implies endorsement.")


# -- the tables the builder and the live scoreboard use ------------------------------------------

def board_teams() -> dict[str, str]:
    """{board abbreviation: full name}, from the builder's own `TEAMS`."""
    spec = importlib.util.spec_from_file_location("_fetch_logos_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {abbr: row[0] for abbr, row in module.TEAMS.items()}


def espn_to_board() -> dict[str, str]:
    """`ESPN_TO_BOARD` as web/lib/live.js spells it, read, never edited."""
    text = LIVE_JS.read_text(encoding="utf-8")
    found = re.search(r"export const ESPN_TO_BOARD\s*=\s*\{([^}]*)\}", text)
    if not found:
        raise RuntimeError(f"ESPN_TO_BOARD not found in {LIVE_JS}")
    return dict(re.findall(r"([A-Za-z0-9]+)\s*:\s*\"([A-Za-z0-9]+)\"", found.group(1)))


def plain(name: str) -> str:
    """A name with accents, punctuation and case removed, so "Montreal" finds "Montréal"."""
    folded = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


# -- PNG validation, standard library only -------------------------------------------------------

def png_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) when `data` is a whole, decodable PNG; None otherwise.

    Walks every chunk and checks its CRC, requires IHDR first and IEND last, and inflates the
    concatenated IDAT stream, so a truncated download, an HTML error page or a JPEG never passes.
    """
    if not data.startswith(PNG_SIGNATURE):
        return None
    position, chunks, idat = len(PNG_SIGNATURE), [], []
    while position + 12 <= len(data):
        (length,) = struct.unpack(">I", data[position:position + 4])
        kind = data[position + 4:position + 8]
        body = data[position + 8:position + 8 + length]
        if len(body) != length or position + 12 + length > len(data):
            return None
        (crc,) = struct.unpack(">I", data[position + 8 + length:position + 12 + length])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            return None
        chunks.append(kind)
        if kind == b"IDAT":
            idat.append(body)
        position += 12 + length
        if kind == b"IEND":
            break
    if not chunks or chunks[0] != b"IHDR" or chunks[-1] != b"IEND" or not idat:
        return None
    header = data[len(PNG_SIGNATURE) + 8:len(PNG_SIGNATURE) + 8 + 13]
    width, height = struct.unpack(">II", header[:8])
    try:
        if not zlib.decompress(b"".join(idat)):
            return None
    except zlib.error:
        return None
    return (width, height) if width > 0 and height > 0 else None


def usable(data: bytes) -> bool:
    """A real PNG, more than 2 KB, 500 px on its longer side."""
    size = png_size(data)
    return len(data) > MIN_BYTES and size is not None and max(size) == SIZE_PX


# -- the network ----------------------------------------------------------------------------------

def get(url: str, agent: str | None = None, attempts: int = 4) -> bytes | None:
    """The body of a 200, or None. A 429 or 503 is retried after Retry-After or a doubling pause."""
    headers = {"User-Agent": agent} if agent else {}
    pause = 2.0
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as answer:
                return answer.read() if answer.status == 200 else None
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts - 1:
                print(f"  {url}: HTTP {error.code}", file=sys.stderr)
                return None
            wait = error.headers.get("Retry-After", "")
            time.sleep(min(float(wait), MAX_WAIT) if wait.isdigit() else pause)
            pause *= 2
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"  {url}: {error}", file=sys.stderr)
            return None
    return None


def espn_logos(teams: dict[str, str]) -> dict[str, str]:
    """{board abbreviation: ESPN logo URL} for every ESPN team that maps to a board team."""
    body = get(ESPN_TEAMS)  # urllib's default agent: ESPN 403s a descriptive one
    if body is None:
        return {}
    codes, by_name = espn_to_board(), {plain(name): abbr for abbr, name in teams.items()}
    found: dict[str, str] = {}
    for league in (json.loads(body).get("sports") or [{}])[0].get("leagues") or []:
        for item in league.get("teams") or []:
            team = item.get("team") or {}
            code = team.get("abbreviation") or ""
            abbr = codes.get(code, code)
            if abbr not in teams:
                abbr = by_name.get(plain(team.get("displayName") or ""), "")
            logos = team.get("logos") or []
            if abbr and logos and logos[0].get("href"):
                found.setdefault(abbr, logos[0]["href"])
    return found


def commons_logo(name: str) -> tuple[str, bytes] | None:
    """(thumbnail URL, PNG) for the first SVG/PNG Commons result for "<name> logo" that validates."""
    query = urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": f"{name} logo", "gsrnamespace": 6,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": SIZE_PX, "format": "json",
    })
    body = get(f"{COMMONS_API}?{query}", COMMONS_AGENT)
    if body is None:
        return None
    pages = sorted((json.loads(body).get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for page in pages:
        if not str(page.get("title", "")).lower().endswith((".svg", ".png")):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        thumb = info.get("thumburl")
        if not thumb:
            continue
        data = get(thumb, COMMONS_AGENT)
        if data is not None and usable(data):
            return thumb, data
        return None  # the first SVG/PNG result only, as the drop specifies
    return None


# -- SOURCES.md -----------------------------------------------------------------------------------

ROW = re.compile(r"^\| `([A-Z0-9]+)\.png` \| (.+?) \| <(\S+)> \|$")


def read_sources(dest: Path) -> dict[str, tuple[str, str]]:
    """{abbr: (source, url)} already recorded, so a rerun that skips a file keeps its line."""
    path = dest / "SOURCES.md"
    if not path.exists():
        return {}
    rows = (ROW.match(line) for line in path.read_text(encoding="utf-8").splitlines())
    return {m.group(1): (m.group(2), m.group(3)) for m in rows if m}


def write_sources(dest: Path, sources: dict[str, tuple[str, str]]) -> None:
    lines = [
        "# Team logos: where each file came from",
        "",
        "Written by `web/fetch_logos.py`, which fills this folder once and skips any file that exists.",
        "The site reads `teams[abbr].logo` from board.json, else `./logos/<ABBR>.png`, else shows the",
        "coloured abbreviation.",
        "",
        NOTICE,
        "",
        "| File | Source | URL |",
        "|:-----|:-------|:----|",
    ]
    lines += [f"| `{abbr}.png` | {source} | <{url}> |" for abbr, (source, url) in sorted(sources.items())]
    (dest / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- main -----------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=LOGOS, help="folder to fill (default web/logos)")
    args = parser.parse_args(argv)
    dest: Path = args.dest
    dest.mkdir(parents=True, exist_ok=True)

    teams = board_teams()
    sources = {abbr: row for abbr, row in read_sources(dest).items() if (dest / f"{abbr}.png").exists()}
    wanted = [abbr for abbr in sorted(teams) if not (dest / f"{abbr}.png").exists()]
    print(f"{len(teams) - len(wanted)} of {len(teams)} logos already present; fetching {len(wanted)}.")
    espn = espn_logos(teams) if wanted else {}

    missing: list[str] = []
    for abbr in wanted:
        got: tuple[str, str, bytes] | None = None
        url = espn.get(abbr)
        if url:
            data = get(url)
            if data is not None and usable(data):
                got = ("ESPN", url, data)
        if got is None:
            found = commons_logo(teams[abbr])
            if found:
                got = ("Wikimedia Commons", found[0], found[1])
        if got is None:
            missing.append(abbr)
            print(f"  {abbr}: no source answered; the page shows the abbreviation")
            continue
        source, url, data = got
        partial = dest / f".{abbr}.png.part"
        partial.write_bytes(data)
        partial.replace(dest / f"{abbr}.png")
        sources[abbr] = (source, url)
        print(f"  {abbr}: {source} {url} ({len(data)} bytes)")

    write_sources(dest, sources)
    print(f"{len(sources)} of {len(teams)} teams have a logo." + (f" Missing: {', '.join(missing)}." if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
