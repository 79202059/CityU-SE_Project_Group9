"""Two classes that reach into each other's private state.

``Account`` keeps three private fields; ``Auditor`` reads all three without
any inheritance or composition relationship between them.  That is the
"inappropriate intimacy" shape: shared private knowledge instead of an
interface.
"""


class Account:
    def __init__(self):
        self._balance = 0
        self._owner = ""
        self._currency = "EUR"

    def balance(self):
        return self._balance


class Auditor:
    def __init__(self, account):
        self.account = account

    def summarise(self):
        total = self.account._balance
        owner = self.account._owner
        currency = self.account._currency
        return "%s %s %s" % (owner, total, currency)
