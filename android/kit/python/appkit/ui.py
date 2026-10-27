"""Screen blocks: plain dicts the Kotlin shell draws (`kit/ui/Blocks.kt`). Every block has a type `t`.

Text accepts **bold** (two asterisks). Tones colour values and badges: "good", "bad", "warn", "info", "muted",
or a hex colour ("#2e6fdb"). `open` is a link to another screen: {"screen": name, "args": {...}}.
A screen returns `page(title, *blocks)` (or a plain list of blocks).
"""
from __future__ import annotations

from typing import Any, Iterable

Block = dict[str, Any]


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def link(screen: str, **args: Any) -> dict:
    return {"screen": screen, "args": {k: v for k, v in args.items() if v is not None}}


def page(title: str, *blocks: Block | None | Iterable, subtitle: str | None = None) -> dict:
    return _clean({"title": title, "subtitle": subtitle, "blocks": flatten(blocks)})


def flatten(blocks: Iterable) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        if b is None or b is False:
            continue
        if isinstance(b, dict):
            out.append(b)
        else:
            out.extend(flatten(b))
    return out


# ---- text ---------------------------------------------------------------------------------------------------

def title(text: str, sub: str | None = None) -> Block:
    return _clean({"t": "title", "text": text, "sub": sub})


def text(text: str, style: str = "body") -> Block:
    """style: body, muted, small, big."""
    return {"t": "text", "text": text, "style": style}


def muted(t: str) -> Block:
    return text(t, "muted")


def bullets(items: Iterable[str], style: str = "body") -> Block:
    return {"t": "bullets", "items": [i for i in items if i], "style": style}


def alert(level: str, title: str, text: str | None = None) -> Block:
    """level: rouge/bad, orange/warn, info, vert/good."""
    level = {"rouge": "bad", "orange": "warn", "vert": "good"}.get(level, level)
    return _clean({"t": "alert", "level": level, "title": title, "text": text})


def divider() -> Block:
    return {"t": "divider"}


# ---- figures ------------------------------------------------------------------------------------------------

def metric(label: str, value: str, sub: str | None = None, tone: str | None = None, sub_tone: str | None = None,
           open: dict | None = None) -> dict:
    return _clean({"label": label, "value": value, "sub": sub, "tone": tone, "sub_tone": sub_tone, "open": open})


def metrics(*items: dict | None, columns: int = 2) -> Block:
    return {"t": "metrics", "items": [i for i in items if i], "columns": columns}


def big(label: str, value: str, sub: str | None = None, tone: str | None = None) -> Block:
    return _clean({"t": "big", "label": label, "value": value, "sub": sub, "tone": tone})


def badge(text: str, tone: str | None = None) -> dict:
    return _clean({"text": text, "tone": tone})


def row(title: str, sub: str | None = None, value: str | None = None, tone: str | None = None,
        badge: dict | None = None, open: dict | None = None, action: dict | None = None) -> dict:
    """One line of a list. `action`: {"name", "args", "confirm"} run when tapped."""
    return _clean({"title": title, "sub": sub, "value": value, "tone": tone, "badge": badge, "open": open, "action": action})


def rows(items: Iterable[dict], empty: str | None = None) -> Block:
    items = [i for i in items if i]
    return _clean({"t": "rows", "items": items, "empty": empty})


def card(title: str | None, *blocks: Block | None | Iterable, tone: str | None = None, open: dict | None = None,
         collapsed: bool | None = None) -> Block:
    """A framed group; collapsed=True/False makes it expandable (closed or open at first)."""
    return _clean({"t": "card", "title": title, "tone": tone, "open": open, "collapsed": collapsed, "blocks": flatten(blocks)})


def table(columns: list[str], data: Iterable[Iterable[Any]], tones: list[list[str | None]] | None = None) -> Block:
    """A table that scrolls sideways; cells are shown as text."""
    data = [["—" if c is None else str(c) for c in r] for r in data]
    return _clean({"t": "table", "columns": columns, "rows": data, "tones": tones})


# ---- charts -------------------------------------------------------------------------------------------------

def series(name: str, values: Iterable[float | None], color: str | None = None, style: str = "line") -> dict:
    """style: line, dash, points, bar, area."""
    return _clean({"name": name, "values": [None if v is None or v != v else float(v) for v in values],
                   "color": color, "style": style})


def chart(title: str | None, labels: list[str], *data: dict, kind: str = "line", y: str = "num",
          reverse: bool = False, height: int = 180, bands: list[dict] | None = None, lines: list[dict] | None = None,
          y_min: float | None = None, y_max: float | None = None, highlight: int | None = None) -> Block:
    """kind: line (series drawn by their style), bar, stack (stacked bars), hbar (horizontal bars, one series).
    y: num, int, pace (s/km → m:ss), time (s → h:mm:ss), pct (0-100), hours, km.
    bands: [{"from", "to", "color", "label"}], lines: [{"y", "label", "color"}]; reverse puts small values at the top."""
    return _clean({"t": "chart", "title": title, "kind": kind, "labels": [str(x) for x in labels], "series": list(data),
                   "y": y, "reverse": reverse or None, "height": height, "bands": bands, "lines": lines,
                   "y_min": y_min, "y_max": y_max, "highlight": highlight})


def band(lo: float, hi: float, color: str = "#2e6fdb", label: str | None = None) -> dict:
    return _clean({"from": lo, "to": hi, "color": color, "label": label})


def hline(y: float, label: str | None = None, color: str = "#6b7280") -> dict:
    return _clean({"y": y, "label": label, "color": color})


def route(points: list[list[float]], values: list[float] | None = None, height: int = 220, label: str | None = None) -> Block:
    """A GPS track drawn on its own (no map tiles); `values` colour it (e.g. pace)."""
    return _clean({"t": "route", "points": points, "values": values, "height": height, "label": label})


# ---- interaction --------------------------------------------------------------------------------------------

def choice(name: str, options: Iterable[tuple[Any, str]], value: Any, label: str | None = None) -> Block:
    """Chips; picking one reloads the screen with `name` set to that option's value."""
    return _clean({"t": "choice", "name": name, "label": label, "value": value,
                   "options": [{"value": v, "label": lab} for v, lab in options]})


def pager(label: str, prev: dict | None, next: dict | None) -> Block:
    """« ‹ label › »: prev/next are screen args (merged into the current ones) or None when unavailable."""
    return _clean({"t": "pager", "label": label, "prev": prev, "next": next})


def button(label: str, action: str, args: dict | None = None, confirm: str | None = None, style: str = "primary",
           icon: str | None = None) -> Block:
    """style: primary, secondary, danger, text."""
    return _clean({"t": "button", "label": label, "action": action, "args": args or {}, "confirm": confirm,
                   "style": style, "icon": icon})


def buttons(*items: Block | None) -> Block:
    return {"t": "buttons", "items": [i for i in items if i]}


def field(name: str, label: str, kind: str = "text", value: Any = "", options: Iterable[tuple[Any, str]] | None = None,
          help: str | None = None, placeholder: str | None = None) -> dict:
    """kind: text, number, decimal, secret, multiline, date (AAAA-MM-JJ), time (HH:MM), select, toggle, multi."""
    return _clean({"name": name, "label": label, "kind": kind, "value": value, "help": help, "placeholder": placeholder,
                   "options": [{"value": v, "label": lab} for v, lab in options] if options is not None else None})


def form(fields: list[dict], action: str, submit: str = "Enregistrer", args: dict | None = None,
         confirm: str | None = None, live: bool = False) -> Block:
    """The fields' values are sent to `action` as keyword arguments (with `args`).
    live=True: the submit button reloads the screen with the values as screen args (forms that preview)."""
    return _clean({"t": "form", "fields": fields, "action": action, "submit": submit, "args": args or {},
                   "confirm": confirm, "live": live or None})


def file_button(label: str, action: str, mime: str = "*/*", args: dict | None = None, confirm: str | None = None) -> Block:
    """Pick a document; the app copies it to its cache and calls `action(path=…, name=…, **args)`."""
    return _clean({"t": "file", "label": label, "action": action, "mime": mime, "args": args or {}, "confirm": confirm})


def export_button(label: str, action: str, filename: str, mime: str = "application/octet-stream") -> Block:
    """Save a file where Jules chooses: `action(dest=…)` writes it, the app then copies it to the chosen place."""
    return {"t": "export", "label": label, "action": action, "filename": filename, "mime": mime}


def sync_status(last: str | None, running_text: str = "Synchronisation en cours…") -> Block:
    """The sync button with its state (the shell knows whether a sync runs)."""
    return _clean({"t": "sync", "last": last, "running": running_text})
