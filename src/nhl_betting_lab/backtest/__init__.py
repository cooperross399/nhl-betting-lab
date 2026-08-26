"""Walk-forward measurement. Nothing here ever scores a model on data it saw."""


def samples_are_current(
    samples, *, known_markets, required_columns=()
) -> tuple[bool, str]:
    """Whether cached samples can stand in for freshly generated ones.

    Three ways a cache goes stale, each found the hard way:

    * **A market was renamed.** The CSV keeps the old key, the report groups
      by it, and the output describes a market that no longer exists.
    * **A market was added.** The cache simply lacks it, every price for it
      finds no model opinion, and the brand-new market measures as empty — a
      verdict that looks like the provider's fault and is the cache's.
    * **The schema changed.** Old columns under new code either crash or, far
      worse, half-work.

    Reusing samples is a speed optimisation and must never be a correctness
    one, so any of the three regenerates rather than trusts.
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
    return True, ""
