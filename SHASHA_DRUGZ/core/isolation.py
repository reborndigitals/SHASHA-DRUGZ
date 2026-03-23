# SHASHA_DRUGZ/core/isolation.py
# =====================================================
# BOT ISOLATION ENGINE
# =====================================================
# How it works:
#   1. deploy.py calls _register_isolation_handlers()
#      after each bot_client.start(). That registers a
#      group=-1000 handler on the specific client instance
#      (NOT on the Client class) that sets _current_bot_id
#      before every update.
#
#   2. IsolatedDatabase wraps motor db. Any collection
#      access auto-prefixes  bot_{id}_  when a deployed
#      bot ContextVar is active. Main bot gets no prefix.
#
#   3. 500+ modules need ZERO changes. They import
#      `mongodb` normally and automatically get the right
#      isolated collection.
#
# NO middleware plugin file needed. No import errors.
# =====================================================

from __future__ import annotations
from contextvars import ContextVar
from typing import Optional, Dict

# ── Shared owner cache  (deploy.py populates this) ───────────────────────────
_owner_cache: Dict[int, int] = {}   # bot_id → owner_id

# ── Per-async-task bot context ────────────────────────────────────────────────
_current_bot_id: ContextVar[Optional[int]] = ContextVar(
    "current_bot_id", default=None
)
_current_bot_owner: ContextVar[Optional[int]] = ContextVar(
    "current_bot_owner", default=None
)


def set_bot_context(bot_id: int, owner_id: Optional[int] = None):
    """Set isolation context for the current asyncio task."""
    _current_bot_id.set(bot_id)
    _current_bot_owner.set(owner_id)


def get_current_bot_id() -> Optional[int]:
    return _current_bot_id.get()


def get_current_bot_owner() -> Optional[int]:
    return _current_bot_owner.get()


def is_deployed_bot() -> bool:
    return _current_bot_id.get() is not None


# ── Isolated async MongoDB proxy ──────────────────────────────────────────────

class IsolatedDatabase:
    """
    Wraps a Motor AsyncIOMotorDatabase.
    Transparently prefixes collection names with bot_{id}_
    when a deployed-bot ContextVar is active.

      Main bot  →  db["chatbot_status"]          (unchanged)
      Bot 111   →  db["bot_111_chatbot_status"]
      Bot 222   →  db["bot_222_chatbot_status"]

    No module code needs to change.
    """

    # Attributes that must pass through to the real db object unchanged
    _PASSTHROUGH = frozenset({
        "_real_db", "client", "codec_options", "read_preference",
        "write_concern", "read_concern", "name", "id",
    })

    def __init__(self, real_db):
        object.__setattr__(self, "_real_db", real_db)

    def _resolve(self, name: str) -> str:
        bot_id = _current_bot_id.get()
        if bot_id is not None:
            return f"bot_{bot_id}_{name}"
        return name

    def _get_col(self, name: str):
        real_db = object.__getattribute__(self, "_real_db")
        return real_db[self._resolve(name)]

    def __getattr__(self, name: str):
        # Pass through private/dunder and known Motor attributes unchanged
        if name.startswith("_") or name in self._PASSTHROUGH:
            real_db = object.__getattribute__(self, "_real_db")
            return getattr(real_db, name)
        return self._get_col(name)

    def __getitem__(self, name: str):
        return self._get_col(name)

    def __repr__(self):
        bot_id  = _current_bot_id.get()
        real_db = object.__getattribute__(self, "_real_db")
        ctx = f"bot_{bot_id}" if bot_id else "main"
        return f"<IsolatedDatabase ctx={ctx!r} db={real_db!r}>"


# ── Isolated sync MongoDB proxy ───────────────────────────────────────────────

class IsolatedSyncDatabase:
    """Same concept for PyMongo (sync)."""

    _PASSTHROUGH = frozenset({
        "_real_db", "client", "codec_options", "read_preference",
        "write_concern", "read_concern", "name",
    })

    def __init__(self, real_db):
        object.__setattr__(self, "_real_db", real_db)

    def _resolve(self, name: str) -> str:
        bot_id = _current_bot_id.get()
        if bot_id is not None:
            return f"bot_{bot_id}_{name}"
        return name

    def __getattr__(self, name: str):
        if name.startswith("_") or name in self._PASSTHROUGH:
            real_db = object.__getattribute__(self, "_real_db")
            return getattr(real_db, name)
        real_db = object.__getattribute__(self, "_real_db")
        return real_db[self._resolve(name)]

    def __getitem__(self, name: str):
        real_db = object.__getattribute__(self, "_real_db")
        return real_db[self._resolve(name)]

    def __repr__(self):
        bot_id  = _current_bot_id.get()
        real_db = object.__getattribute__(self, "_real_db")
        ctx = f"bot_{bot_id}" if bot_id else "main"
        return f"<IsolatedSyncDatabase ctx={ctx!r} db={real_db!r}>"
