"""American odds arithmetic, in one place so nothing re-derives it badly.

Every function here refuses a nonsense price rather than returning a plausible
number for it. A silently wrong implied probability is a wrong edge on every
line of the card.
"""

from __future__ import annotations

import math


class OddsError(ValueError):
    """A price that cannot be interpreted as American odds."""


def _as_price(value: object) -> float:
    if isinstance(value, bool):
        raise OddsError(f"{value!r} is not an American price.")
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise OddsError(f"{value!r} is not an American price.") from exc
    if not math.isfinite(price):
        raise OddsError("An American price must be finite.")
    # There is no such thing as a price between -100 and +100 exclusive.
    if -100 < price < 100:
        raise OddsError(f"{price:g} is not a valid American price.")
    return price


def american_to_implied(value: object) -> float:
    """Implied probability of a single American price, juice included."""
    price = _as_price(value)
    if price > 0:
        return 100.0 / (price + 100.0)
    return -price / (-price + 100.0)


def american_to_decimal(value: object) -> float:
    """Decimal odds, i.e. total return per unit staked."""
    price = _as_price(value)
    if price > 0:
        return 1.0 + price / 100.0
    return 1.0 + 100.0 / -price


def implied_to_american(probability: float) -> int:
    """The American price a probability corresponds to, rounded to an integer.

    Used for the "fair price" column. It is a presentation number: it says
    what the model thinks the line should be, never what anyone will pay.
    """
    p = float(probability)
    if not 0.0 < p < 1.0:
        raise OddsError("A fair price needs a probability strictly between 0 and 1.")
    if p >= 0.5:
        return -int(round(100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def profit_on_win(value: object, stake: float = 1.0) -> float:
    """Profit (not total return) from a winning bet of `stake` units."""
    return (american_to_decimal(value) - 1.0) * float(stake)


def devig_two_way(over_price: object, under_price: object) -> tuple[float, float]:
    """Remove the vig from a two-sided market, proportionally.

    Only valid when both sides are quoted. Most prop markets quote one side
    only, which is exactly why `no_vig_available` exists: pretending a
    one-sided quote can be devigged would manufacture a fair probability out
    of nothing.
    """
    over = american_to_implied(over_price)
    under = american_to_implied(under_price)
    total = over + under
    if total <= 0:
        raise OddsError("A two-way market cannot have zero implied probability.")
    return over / total, under / total


def no_vig_available(over_price: object, under_price: object | None) -> bool:
    """Whether both sides exist, so a devig is honest rather than invented."""
    if under_price is None:
        return False
    try:
        american_to_implied(over_price)
        american_to_implied(under_price)
    except OddsError:
        return False
    return True


def edge(model_probability: float, price: object) -> float:
    """Model probability minus the price's implied probability.

    On a one-sided prop quote the implied probability includes the vig, which
    **overstates** the true probability and therefore **understates** this
    number. The measurement is conservative in that one direction, and every
    report that uses it says so.
    """
    return float(model_probability) - american_to_implied(price)


def expected_value(
    model_probability: float, price: object, stake: float = 1.0
) -> float:
    """Expected profit in units from staking `stake` at `price`."""
    p = float(model_probability)
    if not 0.0 <= p <= 1.0:
        raise OddsError("A probability must lie in [0, 1].")
    return p * profit_on_win(price, stake) - (1.0 - p) * float(stake)


def is_heavy_juice(value: object, limit: int) -> bool:
    """Whether a price is worse than the configured juice limit.

    `limit` is negative (e.g. -160). A price of -180 is heavier than -160; a
    plus-money price never is.
    """
    price = _as_price(value)
    if price > 0:
        return False
    return price < float(limit)
