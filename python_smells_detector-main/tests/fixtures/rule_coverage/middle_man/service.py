"""A class whose only job is to forward to somebody else.

``OrderService`` delegates three of its four methods straight to ``_repo``
and adds nothing of its own.  The name deliberately avoids the
Proxy/Delegate/Adapter/Facade suffixes the detector already whitelists.
"""


class Repository:
    def find(self, key):
        return {"key": key}

    def save(self, payload):
        return payload

    def delete(self, key):
        return key

    def count(self):
        return 0


class OrderService:
    def __init__(self, repo):
        self._repo = repo
        self.created = 0

    def find(self, key):
        return self._repo.find(key)

    def save(self, payload):
        return self._repo.save(payload)

    def delete(self, key):
        return self._repo.delete(key)

    def count(self):
        self.created = self.created + 1
        return self._repo.count()
