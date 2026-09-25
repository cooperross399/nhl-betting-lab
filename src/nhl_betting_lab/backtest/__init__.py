"""Walk-forward measurement. Nothing here ever scores a model on data it saw."""


def policy_mismatch(samples, required_policy) -> str:
    """Why `samples` were not generated under `required_policy`, or "".

    `required_policy` maps a column the generator records on every row (today
    `use_rest`) to the value the recorded verdict now calls for. A cache that
    records no such column cannot say which policy made it, and is refused
    like one that says the wrong one.
    """
    for column, wanted in (required_policy or {}).items():
        if column not in samples.columns:
            return (
                f"the cached samples record no `{column}`, so nothing says "
                "which policy generated them. They predate the record and "
                "may describe a policy the card does not run."
            )
        # Compared as text, because a CSV round trip may hand back a bool, a
        # numpy bool or the string "True" for the same value.
        seen = {
            str(value).strip().lower() for value in samples[column].tolist()
        }
        if seen != {str(wanted).strip().lower()}:
            return (
                f"the cached samples were generated under `{column}` = "
                f"{sorted(seen)}, and the recorded verdict now calls for "
                f"{wanted}. Reusing them would measure a policy the card "
                "does not run."
            )
    return ""


def unpriced_games(samples, source_games) -> str:
    """Why `samples` do not cover the games in `source_games`, or "".

    Every game dated on or after the cache's first sampled date must be in
    it. Games before that date are the warm-up history the first refit was
    fitted on and are never priced. This catches games added at the end of
    a season and games backfilled into its middle (a cold boxscore cache
    fills 600 games a run). It does not catch older games backfilled before
    the first sampled date, which can move that date earlier; and a game the
    generator itself cannot price makes every reuse regenerate, which is
    slow and never wrong.
    """
    import pandas as pd

    needed = {"game_id", "date"}
    if (
        source_games is None
        or source_games.empty
        or not needed <= set(source_games.columns)
        or not needed <= set(samples.columns)
    ):
        return (
            "the cached samples' reach cannot be checked: there are no source "
            "games with a date and a game id to hold them against."
        )
    first = samples["date"].astype(str).str.slice(0, 10).min()
    dates = source_games["date"].astype(str).str.slice(0, 10)
    wanted = pd.to_numeric(
        source_games.loc[dates >= first, "game_id"], errors="coerce"
    )
    have = set(
        pd.to_numeric(samples["game_id"], errors="coerce").dropna().astype(int)
    )
    missing = sorted(set(wanted.dropna().astype(int)) - have)
    if not missing:
        return ""
    latest = dates[
        pd.to_numeric(source_games["game_id"], errors="coerce").isin(missing)
    ].max()
    return (
        f"the cached samples never priced {len(missing):,} game(s) the logs "
        f"now hold, the latest {latest}. They predate those games, and "
        "reusing them leaves every one out of the measurement and the live "
        "corrections."
    )


def samples_are_current(
    samples,
    *,
    known_markets,
    required_columns=(),
    required_lines=None,
    required_policy=None,
    source_games=None,
) -> tuple[bool, str]:
    """Whether cached samples can stand in for freshly generated ones.

    Six ways a cache goes stale, each found the hard way:

    * **A market was renamed.** The CSV keeps the old key, the report groups
      by it, and the output describes a market that no longer exists.
    * **A market was added.** The cache simply lacks it, every price for it
      finds no model opinion, and the brand-new market measures as empty — a
      verdict that looks like the provider's fault and is the cache's.
    * **The schema changed.** Old columns under new code either crash or, far
      worse, half-work.
    * **The line grid widened.** The CI state artifact restores the previous
      run's samples forever, so a pre-widening cache keeps reproducing the
      exact biased measurement the widening closed — counted, but biased.
    * **The policy changed.** Samples generated with the back-to-back
      adjustment on and off have identical columns, and this checked only
      the four above, so after a verdict flipped the old policy's cache went
      on being reused: a rest-ignored prop cache passed while `props_b2b`
      shipped, although 194,707 of its 749,115 rows carry a different fitted
      mean, and the calibration report and live corrections were rebuilt on
      it. `required_policy` (see `policy_mismatch`) is the recorded verdict.
    * **The logs moved on.** Nothing compared the cache with the games it
      was built from, so a cache cut at 2025-12-31 was reused against logs
      reaching 2026-04-16 (605,218 of 749,115 samples) and no game played
      after a cache was built ever reached the calibration. `source_games`
      (see `unpriced_games`) is what a regeneration would read.

    Reusing samples is a speed optimisation and must never be a correctness
    one, so any of the six regenerates rather than trusts. The last two are
    checked only when the caller passes them.
    """
    if samples.empty or "market" not in samples.columns:
        return False, "the cached samples are empty or have no market column"
    missing_columns = sorted(set(required_columns) - set(samples.columns))
    if missing_columns:
        return False, (
            f"the cached samples lack the columns {missing_columns}. They "
            "predate a schema change and would half-work at best."
        )
    found = {str(value).strip() for value in samples["market"].unique()}
    unknown = sorted(found - set(known_markets))
    if unknown:
        return False, (
            f"the cached samples name markets this lab no longer knows: "
            f"{unknown}. They predate a rename and would describe a market "
            "that does not exist."
        )
    absent = sorted(set(known_markets) - found)
    if absent:
        return False, (
            f"the cached samples hold nothing for {absent}. They predate the "
            "market being added, and reusing them would measure it as empty — "
            "a verdict that looks like the provider's fault and is the "
            "cache's."
        )
    if required_lines:
        if "line" not in samples.columns:
            return False, "the cached samples carry no line column"
        for market, lines in required_lines.items():
            have = {
                abs(float(value))
                for value in samples[samples["market"] == market][
                    "line"
                ].dropna()
            }
            missing = sorted(
                {abs(float(value)) for value in lines} - have
            )
            if missing:
                return False, (
                    f"the cached `{market}` samples lack lines {missing} "
                    "that the current grid prices. They predate a grid "
                    "widening and would reproduce the biased measurement it "
                    "closed."
                )
    if required_policy:
        mismatch = policy_mismatch(samples, required_policy)
        if mismatch:
            return False, mismatch
    if source_games is not None:
        gap = unpriced_games(samples, source_games)
        if gap:
            return False, gap
    return True, ""
