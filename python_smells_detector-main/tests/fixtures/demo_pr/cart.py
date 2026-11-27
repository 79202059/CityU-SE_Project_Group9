"""Shopping cart used as the untouched background of the demo."""


class Cart:
    """Keeps the line items of a single customer."""

    def __init__(self):
        self.lines = []

    def add(self, price, qty=1):
        self.lines.append({"price": price, "qty": qty})

    def total(self):
        return sum(line["price"] * line["qty"] for line in self.lines)
