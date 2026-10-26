"""appkit: the Python half of the Android kit (`android/kit`).

An app is a Python package that declares its screens and actions with an `App`; the Kotlin shell of the kit
draws every screen from the blocks it returns (`appkit.ui`). Nothing here depends on Android: screens and
actions are plain functions, tested on the PC like the rest of the engine.

    from appkit import App, ui
    app = App("Carnet de course", tabs=[("aujourdhui", "Aujourd'hui", "today"), ...])

    @app.screen("aujourdhui")
    def today():
        return ui.page("Aujourd'hui", ui.text("Bonjour"))
"""
from appkit.app import App, Result

__all__ = ["App", "Result"]
KIT_VERSION = "1.0.0"
