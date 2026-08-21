"""Single shared slowapi ``Limiter`` for the whole application.

Both the FastAPI app state (``app.state.limiter``) and every route decorator
must reference the same instance so rate-limit counters and headers are
managed by one storage.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
