"""Walk-forward measurement. Nothing here ever scores a model on data it saw."""


def samples_are_current(samples, *, known_markets) -> tuple[bool, str]:
    """Whether cached samples still describe markets this lab knows about.

    A market rename invalidates every cached sample silently: the CSV keeps
    the old key, the report groups by it, and the output describes a market
    that no longer exists. Reusing samples is a speed optimisation and must
    never be a correctness one, so a stale file is regenerated rather than
    trusted.
    """
    if samples.empty or "market" not in samples.columns:
        return False, "the cached samples are empty or have no market column"
    found = {str(value).strip() for value in samples["market"].unique()}
    unknown = sorted(found - set(known_markets))
    if unknown:
        return False, (
            f"the cached samples name markets this lab no longer knows: "
            f"{unknown}. They predate a rename and would describe a market "
            "that does not exist."
        )
    return True, ""
