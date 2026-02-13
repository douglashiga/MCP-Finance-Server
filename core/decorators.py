import os
from functools import wraps
from .connection import ib_conn

IB_ENABLED = os.environ.get("IB_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def require_connection(func):
    """Ensures IB Gateway is connected before executing the decorated function."""
    func.__ib_required__ = True

    @wraps(func)
    async def wrapper(*args, **kwargs):
        wrapper.__ib_required__ = True

        if not IB_ENABLED:
            return {
                "success": False,
                "error": {
                    "code": "ib_disabled",
                    "message": "IBKR features are disabled (IB_ENABLED=false).",
                    "details": {
                        "hint": "Enable IB_ENABLED=true to use real-time IBKR tools.",
                    },
                },
            }
        try:
            await ib_conn.ensure_connection()
        except ConnectionError:
            return {
                "success": False,
                "error": {
                    "code": "ib_not_connected",
                    "message": "Not connected to IB Gateway",
                    "details": None,
                },
            }
        return await func(*args, **kwargs)
    return wrapper
