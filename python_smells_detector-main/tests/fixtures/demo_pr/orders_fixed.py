"""Order processing introduced by the demo pull request."""

TAX_RATES = {
    "standard": 0.20,
    "reduced": 0.05,
    "zero": 0.0,
}

SHIPPING_TIERS = (
    (20.0, 4.95),
    (50.0, 2.95),
)

EXPRESS_SURCHARGE = 9.5


def validate_orders(orders):
    """Reject orders without lines before pricing runs."""
    for order in orders:
        if not order.get("lines"):
            raise ValueError("order %r has no lines" % order.get("id"))


def _discounted(line):
    """Apply the per-line discount and the bundle and import adjusters."""
    price = line["price"]
    discount = line.get("discount", 0.0)
    if discount:
        price = price * (1.0 - discount)
    if line.get("bundle", 1) > 1:
        price = price * 0.9
    if line.get("imported"):
        price = price * 1.08
    return price


def _subtotal(order):
    """Sum the adjusted line prices of one order."""
    return sum(_discounted(line) * line["qty"] for line in order["lines"])


def _rate(order, tax_rate):
    """Return the tax rate, letting the country override the invoice default."""
    country = order.get("country")
    if country == "NO":
        return 0.25
    if country == "CH":
        return 0.077
    return TAX_RATES.get(tax_rate, 0.0)


def _shipping(order, subtotal):
    """Return the shipping fee for the given subtotal."""
    fee = 0.0
    if subtotal < SHIPPING_TIERS[0][0]:
        fee = SHIPPING_TIERS[0][1]
    elif subtotal < SHIPPING_TIERS[1][0]:
        fee = SHIPPING_TIERS[1][1]
    if order.get("express"):
        fee = fee + EXPRESS_SURCHARGE
    return fee


def _row(order, tax_rate):
    """Turn one order into the row that ends up in the invoice."""
    subtotal = _subtotal(order)
    tax = subtotal * _rate(order, tax_rate)
    shipping = _shipping(order, subtotal)
    total = subtotal + tax + shipping
    note = ""
    if total > 100.0:
        note = "review"
    elif total > 50.0:
        note = "standard"
    return {
        "order": order["id"],
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "shipping": round(shipping, 2),
        "total": round(total, 2),
        "note": note,
        "country": order.get("country"),
        "lines": len(order["lines"]),
        "express": bool(order.get("express")),
        "bundle": order.get("bundle", 1),
        "rate": _rate(order, tax_rate),
    }


def process_orders(orders, *, tax_rate="standard"):
    """Price every order and return one summary row per order."""
    validate_orders(orders)
    return [_row(order, tax_rate) for order in orders]


def summarize(rows):
    """Aggregate the per-order rows into one line for the invoice header."""
    total = sum(row["total"] for row in rows)
    tax = sum(row["tax"] for row in rows)
    return {"orders": len(rows), "total": round(total, 2), "tax": round(tax, 2)}
