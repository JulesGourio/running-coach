"""Secrets (COROS web-API credentials), never in the database or the code.

On the PC they stay in `.env` (read by `config`); the phone installs its Android Keystore backend at start
(`mobile.init`). A backend is any object with ``get(name)``, ``set(name, value)`` and ``delete(name)``.
"""
from __future__ import annotations

from typing import Protocol

KNOWN = {
    "coros_email": "E-mail du compte COROS (API web, au-delà de 50 fichiers FIT par jour)",
    "coros_password": "Mot de passe COROS (API web)",
}


class Backend(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...  # noqa: A003
    def delete(self, name: str) -> None: ...


class NoBackend:
    """PC default: nothing stored here, `.env` is the source."""

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None:  # noqa: A003
        raise RuntimeError("Pas de coffre de secrets sur le PC : renseigne le fichier .env.")

    def delete(self, name: str) -> None:
        pass


class MemoryBackend:
    """For tests."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:  # noqa: A003
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


_backend: Backend = NoBackend()


def use(backend: Backend) -> None:
    global _backend
    _backend = backend


def get(name: str) -> str | None:
    return _backend.get(name)


def set(name: str, value: str) -> None:  # noqa: A001
    _backend.set(name, value)


def delete(name: str) -> None:
    _backend.delete(name)
