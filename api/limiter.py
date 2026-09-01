"""Shared slowapi Limiter instance.

Lives in its own module (rather than api/main.py) so route modules can import
it for per-endpoint @limiter.limit(...) decorators without a circular import
back to main.py (which imports the route modules).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
