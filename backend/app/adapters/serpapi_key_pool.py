"""Thread-safe, process-local SerpApi credential selection.

Use only credentials whose owners permit use in this application and within the
provider's allowed usage terms. Keys and request URLs must never be logged.
"""

from threading import Lock
from time import monotonic


class SerpApiKeyPool:
    def __init__(self, keys, *, clock=monotonic):
        # Preserve explicit priority while preventing a duplicate from counting twice.
        self._keys = list(dict.fromkeys(key.strip() for key in keys if key and key.strip()))
        self._clock = clock
        self._lock = Lock()
        self._cursor = 0
        self._blocked_until = {}

    @property
    def count(self):
        return len(self._keys)

    def acquire(self, *, tried=()):
        """Choose an eligible key, without revealing it in diagnostics."""
        excluded = set(tried)
        with self._lock:
            now = self._clock()
            for _ in range(len(self._keys)):
                index = self._cursor % len(self._keys)
                self._cursor = (index + 1) % len(self._keys)
                key = self._keys[index]
                if key not in excluded and self._blocked_until.get(key, 0) <= now:
                    return key
            return None

    def pause(self, key, seconds):
        """Temporarily stop using a credential after provider quota exhaustion."""
        with self._lock:
            self._blocked_until[key] = max(
                self._blocked_until.get(key, 0), self._clock() + max(1, seconds)
            )

    def disable(self, key):
        """Quarantine a revoked/invalid key until the process is reconfigured."""
        with self._lock:
            self._blocked_until[key] = float("inf")

    def available_count(self):
        with self._lock:
            now = self._clock()
            return sum(self._blocked_until.get(key, 0) <= now for key in self._keys)
