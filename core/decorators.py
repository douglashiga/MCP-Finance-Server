from functools import wraps
from .connection import ib_conn


def require_connection(func):
    """Ensures IB Gateway is connected before executing the decorated function."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            await ib_conn.ensure_connection()
        except ConnectionError:
            return {"success": False, "error": "Not connected to IB Gateway"}
        return await func(*args, **kwargs)
    return wrapper
