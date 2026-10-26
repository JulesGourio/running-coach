"""The app's declaration: screens, actions, tabs, start-up and background sync."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Result:
    """What an action returns. Every field is optional:
    - message: shown in a snackbar;
    - reload: redraw the current screen (default);
    - back: leave the current screen;
    - open: {"screen": name, "args": {...}} to open another screen;
    - webauth: {"url": ..., "prefix": ..., "finish": action name, "title": ...} to sign in on a web page whose
      redirect (an address starting with `prefix`) is handed to the `finish` action as `url`;
    - sync: start the background sync now.
    """
    message: str | None = None
    reload: bool = True
    back: bool = False
    open: dict | None = None
    webauth: dict | None = None
    sync: bool = False

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, False) or k == "reload"}


@dataclass
class App:
    title: str
    tabs: list[tuple[str, str, str]]  # (screen, label, icon)
    lock: bool = True  # fingerprint lock after 5 minutes away
    sync_hour: int = 7
    sync_minute: int = 30
    screens: dict[str, Callable[..., Any]] = field(default_factory=dict)
    actions: dict[str, Callable[..., Any]] = field(default_factory=dict)
    start_fn: Callable[..., Any] | None = None
    sync_fn: Callable[[], Any] | None = None

    def screen(self, name: str) -> Callable:
        def deco(fn: Callable) -> Callable:
            self.screens[name] = fn
            return fn
        return deco

    def action(self, name: str) -> Callable:
        def deco(fn: Callable) -> Callable:
            self.actions[name] = fn
            return fn
        return deco

    def on_start(self, fn: Callable) -> Callable:
        """`fn(data_dir, secrets, notifier)` once per process: point the engine at its folder, install backends."""
        self.start_fn = fn
        return fn

    def on_sync(self, fn: Callable) -> Callable:
        """`fn() -> list[str]`: the background sync (daily at sync_hour:sync_minute, and the « Synchroniser » button)."""
        self.sync_fn = fn
        return fn

    def manifest(self) -> dict:
        return {"title": self.title, "lock": self.lock, "sync": {"hour": self.sync_hour, "minute": self.sync_minute},
                "tabs": [{"screen": s, "label": label, "icon": icon} for s, label, icon in self.tabs],
                "screens": sorted(self.screens), "actions": sorted(self.actions)}
