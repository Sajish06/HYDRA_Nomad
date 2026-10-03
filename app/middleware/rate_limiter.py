"""
Rate Limiter Middleware for Public Endpoints.
Implements token bucket / window rate limiting.
"""

from typing import Dict, Tuple
import time

class SimpleRateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, list] = {}

    def is_allowed(self, client_ip: str) -> Tuple[bool, int]:
        """
        Check if request from client_ip is allowed under the rate limit.
        Returns (allowed, remaining_requests).
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean history
        reqs = [t for t in self._history.get(client_ip, []) if t > window_start]

        if len(reqs) >= self.max_requests:
            self._history[client_ip] = reqs
            return False, 0

        reqs.append(now)
        self._history[client_ip] = reqs
        return True, self.max_requests - len(reqs)
