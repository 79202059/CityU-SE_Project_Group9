"""Plain accessor-only value holder.

Only ``get_``/``set_`` methods, four of them, no behaviour of its own.
"""


class Customer:
    def __init__(self):
        self._name = ""
        self._email = ""
        self._phone = ""

    def get_name(self):
        return self._name

    def set_name(self, value):
        self._name = value

    def get_email(self):
        return self._email

    def set_email(self, value):
        self._email = value

    def get_phone(self):
        return self._phone

    def set_phone(self, value):
        self._phone = value
