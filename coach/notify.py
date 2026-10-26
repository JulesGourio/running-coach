"""Notifications: the phone's own on Android (handler installed by `mobile.init`), none on the PC."""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)
_local: Callable[[str, str, int], bool] | None = None


def set_local(handler: Callable[[str, str, int], bool] | None) -> None:
    global _local
    _local = handler


def send(title: str, message: str, priority: int = 3) -> bool:
    """Show a notification; priority 4 or more is urgent. Returns whether it was shown."""
    if _local is None:
        log.info("notification (non affichée) : %s — %s", title, message)
        return False
    try:
        return bool(_local(title, message, priority))
    except Exception:  # noqa: BLE001 - a notification never breaks a sync
        log.exception("notification impossible")
        return False
