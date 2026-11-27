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


def process_orders(orders, *, tax_rate="standard"):
    """Price every order and return one summary row per order."""
    rows = []
    for order in orders:
        subtotal = 0.0
        for line in order["lines"]:
            price = line["price"]
            qty = line["qty"]
            discount = line.get("discount", 0.0)
            if discount:
                price = price * (1.0 - discount)
            bundle = line.get("bundle", 1)
            if bundle > 1:
                price = price * 0.9
            if line.get("imported"):
                price = price * 1.08
            subtotal += price * qty
        rate = TAX_RATES.get(tax_rate, 0.0)
        country = order.get("country")
        if country == "NO":
            rate = 0.25
        elif country == "CH":
            rate = 0.077
        tax = subtotal * rate
        shipping = 0.0
        if subtotal < SHIPPING_TIERS[0][0]:
            shipping = SHIPPING_TIERS[0][1]
        elif subtotal < SHIPPING_TIERS[1][0]:
            shipping = SHIPPING_TIERS[1][1]
        if order.get("express"):
            shipping = shipping + EXPRESS_SURCHARGE
        total = subtotal + tax + shipping
        note = ""
        if total > 100.0:
            note = "review"
        elif total > 50.0:
            note = "standard"
        rows.append(
            {
                "order": order["id"],
                "subtotal": round(subtotal, 2),
                "tax": round(tax, 2),
                "shipping": round(shipping, 2),
                "total": round(total, 2),
                "note": note,
                "country": country,
                "lines": len(order["lines"]),
                "express": bool(order.get("express")),
                "bundle": order.get("bundle", 1),
                "rate": rate,
            }
        )
    return rows


def summarize(rows):
    """Aggregate the per-order rows into one line for the invoice header."""
    total = sum(row["total"] for row in rows)
    tax = sum(row["tax"] for row in rows)
    return {"orders": len(rows), "total": round(total, 2), "tax": round(tax, 2)}
