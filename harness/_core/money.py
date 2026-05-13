from __future__ import annotations
import decimal


def round_half_to_even(amount: float, multiple: int = 500) -> int:
    """Round `amount` to the nearest `multiple` using banker's rounding (ROUND_HALF_EVEN).

    Examples:
        round_half_to_even(750)  -> 1000  (halfway → even → round up to 1000)
        round_half_to_even(1250) -> 1000  (halfway → even → round down to 1000)
        round_half_to_even(1300) -> 1500
        round_half_to_even(200)  -> 0
        round_half_to_even(300)  -> 500
    """
    d = decimal.Decimal(str(amount)) / decimal.Decimal(multiple)
    rounded = int(d.quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_EVEN))
    return rounded * multiple
