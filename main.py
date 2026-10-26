"""CT_2010 Web — punto de entrada (NiceGUI). Ejecutar:  python main.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nicegui import app, ui  # noqa: E402

from webapp import ui_app  # noqa: E402,F401  (registra la página "/")

app.add_static_files("/assets", str(Path(__file__).resolve().parent / "assets"))

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="CT · Comparación de Modelos",
        favicon=str(Path(__file__).resolve().parent / "assets" / "icon.png"),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "7860")),
        reload=False,
        show=False,
        language="es",
        storage_secret=os.environ.get("CT_STORAGE_SECRET", "ct2010-web-cambiar-en-produccion"),
    )
