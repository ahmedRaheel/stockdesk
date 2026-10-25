"""Quantity turnover from daily closing stock; never mixes units or valuation costs."""

from decimal import Decimal
from ..rules import fail


def metrics(rows, days):
    result = []
    for row in rows:
        r = dict(row)
        average = Decimal(r.pop("stock_days")) / days
        opening = Decimal(r["opening"])
        closing = Decimal(r["closing"])
        sold = Decimal(r["sold"])
        returned = Decimal(r["returned"])
        if opening < 0 or closing < 0 or average < 0:
            fail("Stock history is inconsistent; turnover was not generated.", 409)
        net = sold - returned
        turns = net / average if average > 0 else None
        result.append(
            dict(
                **r,
                net_units=net,
                average_stock=average.quantize(Decimal(".000001")),
                turnover=round(turns, 4) if turns is not None else None,
                days_per_turn=(
                    round(Decimal(days) / turns, 2)
                    if turns is not None and turns > 0
                    else None
                )
            )
        )
    return result
