"""
Interfaz web (NiceGUI) de CT_2010: mismo flujo que la versión de
escritorio -- Datos -> elegir métodos -> pestañas de resultados.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path

import pandas as pd
from fastapi import Response
from nicegui import app, run, ui

from ct_tool import io_utils, stats as ct_stats, plots as ct_plots
from .engine import (
    Analysis, APP_VERSION, AUTHOR_CREDIT, AUTHOR_NAME, ESSENTIAL_METHODS, EXTREMES_FIGURE_KEYS,
    METHOD_GROUPS, METHODS_SUMMARY_TITLE, MULTI_KEYS, VALIDATION_FIGURE_KEYS, VALIDATION_INDICATORS, fig_to_png,
)

BASE = Path(__file__).resolve().parent.parent
DEMO = BASE / "data" / "pailas_nam.csv"
QUALITY_COLORS = ct_stats.QUALITY_COLORS
SCALE_CHOICES = {"Normal (100 %)": 1.0, "Grande (112 %)": 1.12, "Muy grande (125 %)": 1.25}

# imágenes por sesión (se sirven por /img/<sesión>/<n>)
_IMGS: dict[str, dict[str, bytes]] = {}


@app.get("/img/{sid}/{name}")
def _img(sid: str, name: str):
    data = _IMGS.get(sid, {}).get(name)
    if data is None:
        return Response(status_code=404)
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


CSS = """
:root { --ct-accent: #3D8BFD; }
body { font-family: 'Inter','Segoe UI',system-ui,sans-serif; }
.ct-card { border-radius: 12px; }
.ct-muted { opacity: .72; }
.ct-mono { font-family: Consolas, 'DejaVu Sans Mono', monospace; background: rgba(61,139,253,.10);
           padding: 8px 12px; border-radius: 8px; white-space: pre-wrap; }
.ct-pre { white-space: pre-wrap; }
.ct-kpi { border-left: 4px solid var(--ct-accent); }
.q-tab__label { font-weight: 600; }
.ct-fig { width: 100%; max-width: 1200px; margin: 0 auto; }
"""


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


@ui.page("/")
def index():
    ui.add_css(CSS)
    a = Analysis()
    sid = uuid.uuid4().hex[:12]
    _IMGS[sid] = {}
    client = ui.context.client
    client.on_disconnect(lambda: _IMGS.pop(sid, None))
    storage = app.storage.browser
    ver = {"n": 0}

    # ------------------------------------------------ preferencias del usuario
    dark = ui.dark_mode(value=bool(storage.get("dark", False)))
    scale = float(storage.get("scale", 1.12))
    a.chart_font = storage.get("chart_font", a.chart_font)
    ask_methods = {"v": bool(storage.get("ask_methods", True))}

    def apply_scale(s: float):
        storage["scale"] = s
        ui.query("body").style(f"font-size: {14 * s:.1f}px;")
    apply_scale(scale)

    ui.colors(primary="#3D8BFD", positive="#1E9E6B", warning="#D8A02A", negative="#DD5353")

    # ------------------------------------------------------------- encabezado
    with ui.header(elevated=True).classes("items-center justify-between q-px-md q-py-xs") \
            .style("background:#0F2742;"):
        with ui.row().classes("items-center no-wrap gap-3"):
            ui.image("/assets/icon.png").classes("w-10 h-10")
            with ui.column().classes("gap-0"):
                ui.label("CT · Comparación de Modelos").classes("text-h6 text-white").style("line-height:1.1")
                ui.label(AUTHOR_CREDIT).classes("text-caption text-blue-2")
        with ui.row().classes("items-center no-wrap gap-2"):
            sel_scale = ui.select(list(SCALE_CHOICES), value=next(
                (k for k, v in SCALE_CHOICES.items() if abs(v - scale) < .01), "Grande (112 %)"),
                label="Texto", on_change=lambda e: apply_scale(SCALE_CHOICES[e.value])) \
                .props("dense outlined dark options-dense").classes("w-40")
            sel_font = ui.select(
                sorted(set(ct_plots.CHART_FONT_PRESETS) | {a.chart_font}), value=a.chart_font,
                label="Letra de gráficos",
                on_change=lambda e: on_font(e.value)).props("dense outlined dark options-dense").classes("w-48")

            ui.button("💾 Guardar", on_click=lambda: save_project()).props("flat color=white no-caps dense") \
                .tooltip("Guardar el proyecto (.ctproj) para continuar después")
            ui.button("📁 Abrir", on_click=lambda: open_project_dialog()).props("flat color=white no-caps dense") \
                .tooltip("Abrir un proyecto .ctproj (también el de la versión de escritorio)")
            ui.button("🖋 Reporte", on_click=lambda: style_dialog()).props("flat color=white no-caps dense") \
                .tooltip("Letra, alineación y estilo de tablas del reporte")
            ui.button("🎨 Colores", on_click=lambda: colors_dialog()).props("flat color=white no-caps dense") \
                .tooltip("Color y tipo de línea de cada corrida/modelo")

            def toggle_dark():
                dark.toggle()
                storage["dark"] = dark.value
                btn_dark.set_text("☀ Claro" if dark.value else "🌙 Oscuro")
            btn_dark = ui.button("☀ Claro" if dark.value else "🌙 Oscuro", on_click=toggle_dark) \
                .props("flat color=white no-caps")

    status = ui.label("Cargue un archivo (o use el ejemplo) para empezar.").classes("ct-muted q-mt-sm")

    with ui.tabs().classes("w-full").props("align=left inline-label") as tabs:
        t_data = ui.tab("datos", label="📋 Datos")
        t_val = ui.tab("val", label="✅ Validación")
        t_vfig = ui.tab("vfig", label="📈 Gráficos de validación")
        t_ext = ui.tab("ext", label="🌊 Extremos (POT)")
        t_multi = ui.tab("multi", label="🧪 Análisis múltiple")
        t_rep = ui.tab("rep", label="📄 Reporte")
    t_multi.set_visibility(False)
    for t in (t_val, t_vfig, t_ext, t_rep):
        t.set_visibility(False)

    panels = ui.tab_panels(tabs, value="datos").classes("w-full").props("keep-alive=false")

    with panels:
        p_data = ui.tab_panel("datos")
        p_val = ui.tab_panel("val")
        p_vfig = ui.tab_panel("vfig")
        p_ext = ui.tab_panel("ext")
        p_multi = ui.tab_panel("multi")
        p_rep = ui.tab_panel("rep")

    # =================================================================== DATOS
    with p_data:
        with ui.row().classes("w-full no-wrap items-start gap-4"):
            left = ui.column().classes("gap-3").style("min-width:340px;max-width:380px;")
            right = ui.column().classes("gap-2 grow").style("min-width:0;")

    grid_holder = {"grid": None}

    def set_status(msg: str, kind: str = "muted"):
        status.set_text(msg)
        status.classes(remove="text-positive text-negative text-warning ct-muted")
        status.classes({"ok": "text-positive", "err": "text-negative", "warn": "text-warning",
                        "muted": "ct-muted"}[kind])

    def df_records(df: pd.DataFrame):
        return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))

    def refresh_grid():
        right.clear()
        with right:
            if a.raw_df is None:
                with ui.card().classes("ct-card w-full items-center q-pa-xl"):
                    ui.label("Aún no hay datos").classes("text-h6")
                    ui.label("Suba un archivo CSV/Excel o pruebe el caso de ejemplo.").classes("ct-muted")
                return
            with ui.row().classes("items-center gap-2"):
                ui.label(f"Tabla de datos (editable) — {a.file_name} · {len(a.raw_df)} filas × "
                         f"{a.raw_df.shape[1]} columnas").classes("text-subtitle1 text-weight-medium")
                ui.space()
                ui.button("+ Fila", on_click=add_row).props("outline dense no-caps")
                ui.button("+ Columna", on_click=add_col).props("outline dense no-caps")
                ui.button("− Última fila", on_click=del_row).props("outline dense no-caps")
            cols = [{"headerName": str(c), "field": str(c), "editable": True, "sortable": True,
                     "resizable": True, "minWidth": 120} for c in a.raw_df.columns]
            grid = ui.aggrid({
                "columnDefs": cols, "rowData": df_records(a.raw_df), "defaultColDef": {"filter": True},
                "rowSelection": {"mode": "singleRow"}, "stopEditingWhenCellsLoseFocus": True,
                "animateRows": False,
            }, theme="balham").classes("w-full").style("height: min(68vh, 640px);")
            grid.on("cellValueChanged", on_cell_changed)
            grid_holder["grid"] = grid

    def on_cell_changed(e):
        d = e.args
        try:
            r, c, v = int(d["rowIndex"]), str(d["colId"]), d["newValue"]
            if pd.api.types.is_numeric_dtype(a.raw_df[c]):
                v = pd.to_numeric(v, errors="coerce")
                a.raw_df.at[r, c] = v
            else:
                try:
                    a.raw_df[c] = a.raw_df[c].astype(object)
                except Exception:
                    pass
                a.raw_df.at[r, c] = v
        except Exception as exc:
            ui.notify(f"No se pudo guardar la edición: {exc}", type="warning")

    def add_row():
        if a.raw_df is None:
            return
        a.raw_df.loc[len(a.raw_df)] = [None] * a.raw_df.shape[1]
        refresh_grid()

    def del_row():
        if a.raw_df is not None and len(a.raw_df) > 1:
            a.raw_df = a.raw_df.iloc[:-1].reset_index(drop=True)
            refresh_grid()

    def add_col():
        if a.raw_df is None:
            return
        with ui.dialog() as dlg, ui.card():
            name = ui.input("Nombre de la columna nueva").props("autofocus")

            def ok():
                n = (name.value or "").strip()
                if not n or n in a.raw_df.columns:
                    ui.notify("Escriba un nombre distinto de los existentes.", type="warning")
                    return
                a.raw_df[n] = float("nan")
                dlg.close()
                refresh_columns()
                refresh_grid()
            with ui.row():
                ui.button("Cancelar", on_click=dlg.close).props("flat")
                ui.button("Agregar", on_click=ok)
        dlg.open()

    def load_df(df: pd.DataFrame, name: str):
        a.load_dataframe(df, name)
        refresh_columns()
        refresh_grid()
        set_status(f"{name} — {len(df)} filas, {df.shape[1]} columnas.")
        for t in (t_val, t_vfig, t_ext, t_rep):
            t.set_visibility(False)
        t_multi.set_visibility(True)
        multi_out.clear()
        refresh_multi_config()

    async def on_upload(e):
        name = e.file.name
        data = await e.file.read()
        tmp = Path("/tmp") / f"ct_{sid}_{Path(name).name}"
        try:
            tmp.write_bytes(data)
            df = await run.io_bound(io_utils.read_table, str(tmp))
            load_df(df, name)
        except Exception as exc:
            ui.notify(f"No se pudo leer el archivo: {exc}", type="negative", multi_line=True)
        finally:
            tmp.unlink(missing_ok=True)

    def load_demo():
        df = io_utils.read_table(str(DEMO))
        load_df(df, "pailas_nam.csv")
        a.date_col, a.obs_col, a.sim_cols = "Fecha", "Observado_m3s", ["Calibracion_m3s"]
        refresh_columns()

    # --- columnas y parámetros
    col_refs = {}
    pot_refs = {}

    def refresh_columns():
        left_cols.clear()
        cols = [str(c) for c in a.raw_df.columns] if a.raw_df is not None else []
        with left_cols:
            col_refs["x"] = ui.select(cols, value=a.date_col if a.date_col in cols else None,
                                      label="Eje X (fecha / profundidad / tiempo) — opcional",
                                      with_input=False, clearable=True,
                                      on_change=lambda e: setattr(a, "date_col", e.value or "")) \
                .classes("w-full")
            ui.label("«Observado» y «Simulado» sirven para cualquier tipo de dato. El Eje X solo hace "
                     "falta para Extremos (POT) y debe ser una fecha.").classes("text-caption ct-muted")
            col_refs["obs"] = ui.select(cols, value=a.obs_col if a.obs_col in cols else None,
                                        label="Observado", on_change=lambda e: setattr(a, "obs_col", e.value or "")) \
                .classes("w-full")
            col_refs["sim"] = ui.select(cols, value=[c for c in a.sim_cols if c in cols], multiple=True,
                                        label="Simulado(s) — una o varias corridas", clearable=True,
                                        on_change=lambda e: setattr(a, "sim_cols", list(e.value or []))) \
                .props("use-chips").classes("w-full")

    with left:
        with ui.card().classes("ct-card w-full"):
            ui.label("1 · Fuente de datos").classes("text-subtitle1 text-weight-bold")
            ui.upload(label="Arrastre aquí un CSV / Excel", auto_upload=True, on_upload=on_upload,
                      max_file_size=60_000_000).props("accept=.csv,.txt,.tsv,.xlsx,.xlsm,.xls flat bordered") \
                .classes("w-full")
            ui.button("📊 Cargar caso de ejemplo (Pailas, NAM)", on_click=load_demo) \
                .props("outline no-caps").classes("w-full")
            ui.button("📋 Pegar datos (desde Excel / texto)", on_click=lambda: paste_dialog()) \
                .props("outline no-caps").classes("w-full")
            ui.button("✍ Empezar con una tabla vacía", on_click=lambda: new_table()) \
                .props("outline no-caps").classes("w-full")
        with ui.card().classes("ct-card w-full"):
            ui.label("2 · Columnas").classes("text-subtitle1 text-weight-bold")
            left_cols = ui.column().classes("w-full gap-2")
        with ui.card().classes("ct-card w-full"):
            ui.label("3 · Parámetros de extremos (POT)").classes("text-subtitle1 text-weight-bold")
            ui.label("Solo se usan si el Eje X es una fecha.").classes("text-caption ct-muted")
            pot_refs["q_max"] = ui.number("Cuantil umbral máximos", value=a.q_max, min=0.5, max=0.999, step=0.01, format="%.3f",
                      on_change=lambda e: setattr(a, "q_max", float(e.value or 0.98))).classes("w-full")
            pot_refs["q_min"] = ui.number("Cuantil umbral mínimos", value=a.q_min, min=0.001, max=0.5, step=0.01, format="%.3f",
                      on_change=lambda e: setattr(a, "q_min", float(e.value or 0.02))).classes("w-full")
            pot_refs["sep"] = ui.number("Separación mínima entre eventos [días]", value=a.sep, min=1, max=3650, step=1,
                      format="%.0f", on_change=lambda e: setattr(a, "sep", int(e.value or 10))).classes("w-full")
            pot_refs["maxev"] = ui.number("Máximo de eventos POT", value=a.maxev, min=5, max=5000, step=5, format="%.0f",
                      on_change=lambda e: setattr(a, "maxev", int(e.value or 150))).classes("w-full")
        with ui.card().classes("ct-card w-full"):
            ui.label("4 · Ejecutar").classes("text-subtitle1 text-weight-bold")
            btn_run = ui.button("▶ Ejecutar análisis", on_click=lambda: on_run_click()) \
                .props("color=primary no-caps unelevated size=lg").classes("w-full")
            ui.button("🧮 Elegir métodos…", on_click=lambda: open_methods(run_after=False)) \
                .props("outline no-caps").classes("w-full")
            ui.label("Los gráficos y el análisis de extremos se generan solos al ejecutar "
                     "(si el Eje X es una fecha).").classes("text-caption ct-muted")
    refresh_columns()
    refresh_grid()

    # ================================================== diálogo de métodos
    def open_methods(run_after: bool):
        checks: dict[str, ui.checkbox] = {}
        with ui.dialog().props("persistent") as dlg, ui.card().classes("ct-card").style(
                "width:min(760px,95vw);max-height:90vh;"):
            ui.label("¿Qué métodos estadísticos desea aplicar?").classes("text-h6")
            ui.label("Solo de los elegidos se generan pestañas de resultados. Los gráficos y los "
                     "extremos (POT, Box-Cox) se generan automáticamente.").classes("ct-muted")

            def set_many(keys):
                for k, c in checks.items():
                    c.set_value(k in keys)
            with ui.row().classes("gap-2"):
                ui.button("Todos", on_click=lambda: set_many(VALIDATION_INDICATORS)).props("outline dense no-caps")
                ui.button("Ninguno", on_click=lambda: set_many([])).props("outline dense no-caps")
                ui.button("Los esenciales", on_click=lambda: set_many(ESSENTIAL_METHODS)).props("outline dense no-caps")
            with ui.scroll_area().classes("w-full").style("height:46vh;"):
                for title, keys in METHOD_GROUPS:
                    ui.label(title).classes("text-subtitle2 text-weight-bold q-mt-sm")
                    for k in keys:
                        with ui.column().classes("gap-0 q-mb-xs"):
                            checks[k] = ui.checkbox(k, value=k in a.selected)
                            teoria = (ct_stats.INDICATOR_HELP.get(k, {}).get("teoria", "") or "").strip()
                            first = teoria.split(". ")[0].strip()
                            if first:
                                ui.label(first + ("." if not first.endswith(".") else "")) \
                                    .classes("text-caption ct-muted q-ml-lg")
            with ui.row().classes("items-center gap-4"):
                kspin = ui.number("k (parámetros calibrados, para SEE)", value=a.see_k, min=0, max=50,
                                  step=1, format="%.0f").classes("w-64")
                ask = ui.checkbox("Preguntar siempre al ejecutar", value=ask_methods["v"])

            async def accept():
                chosen = [k for k in VALIDATION_INDICATORS if checks[k].value]
                if not chosen:
                    ui.notify("Elija al menos un método.", type="warning")
                    return
                a.selected = chosen
                a.see_k = int(kspin.value or 0)
                ask_methods["v"] = bool(ask.value)
                storage["ask_methods"] = ask_methods["v"]
                dlg.close()
                if run_after:
                    await do_run()
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancelar", on_click=dlg.close).props("flat no-caps")
                ui.button("▶ Ejecutar análisis" if run_after else "Aceptar", on_click=accept) \
                    .props("color=primary no-caps unelevated")
        dlg.open()

    async def on_run_click():
        if a.raw_df is None:
            ui.notify("Primero cargue o introduzca datos.", type="warning")
            return
        if not a.obs_col or not a.sim_cols:
            ui.notify("Elija «Observado» y al menos un «Simulado».", type="warning")
            return
        if ask_methods["v"] or not a.selected:
            open_methods(run_after=True)
        else:
            await do_run()

    # ============================================================== EJECUCIÓN
    async def do_run(goto: bool = True):
        with ui.dialog().props("persistent") as busy, ui.card().classes("items-center q-pa-lg"):
            ui.spinner(size="xl")
            ui.label("Calculando indicadores, extremos y gráficos…").classes("q-mt-md")
            ui.label("Puede tardar un momento con series largas.").classes("ct-muted text-caption")
        busy.open()
        try:
            await run.io_bound(a.run)
        except Exception as exc:
            busy.close()
            ui.notify(f"Error en el análisis: {exc}", type="negative", multi_line=True, close_button=True)
            return
        busy.close()
        build_results()
        if a.box_cox_warnings:
            set_status("Análisis ejecutado con aviso: revise la pestaña Extremos (POT).", "warn")
            ui.notify("Box-Cox no disponible para algunos extremos; el resto se calculó normalmente.",
                      type="warning", multi_line=True)
        else:
            set_status(f"✓ Análisis listo: {len(a.ran_selected)} método(s)"
                       + (" + extremos y gráficos." if a.extremes_ran else "."), "ok")
        if a.note:
            ui.notify(a.note, type="info", multi_line=True)
        if goto:
            tabs.set_value("val")

    # ============================================================== RESULTADOS
    def put_imgs():
        """Publica las imágenes de la corrida y devuelve {clave: url}."""
        ver["n"] += 1
        _IMGS[sid].clear()
        urls = {}
        for key, png in list(a.pngs.items()) + list(a.multi_pngs.items()) + [("gauge::" + k, v) for k, v in a.gauge_pngs.items()]:
            name = f"{ver['n']}_{_slug(key)}.png"
            _IMGS[sid][name] = png
            urls[key] = f"/img/{sid}/{name}"
        return urls

    def figure_block(key: str, url: str, height: str | None = None):
        """Gráfico + descripción plegable + ampliar + descargar."""
        desc = ct_plots.FIGURE_DESCRIPTIONS.get(key, "")
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("items-center gap-2"):
                ui.label(key).classes("text-subtitle1 text-weight-medium")
                ui.space()
                ui.button("🔍 Ampliar", on_click=lambda k=key, u=url: zoom(k, u)).props("outline dense no-caps")
                ui.button("⬇ PNG (alta resolución)", on_click=lambda k=key: download_fig(k)) \
                    .props("outline dense no-caps")
            if desc:
                with ui.expansion("ℹ ¿Qué muestra este gráfico?").classes("w-full").props("dense"):
                    ui.label(desc).classes("ct-pre")
            ui.element("img").props(f'src="{url}" alt="{key}"').style(
                "display:block;margin:0 auto;max-width:100%;max-height:66vh;object-fit:contain;")

    def zoom(key: str, url: str):
        with ui.dialog().props("maximized") as dlg, ui.card().classes("w-full items-center") \
                .style("overflow:auto;"):
            with ui.row().classes("w-full items-center"):
                ui.label(key).classes("text-h6")
                ui.space()
                ui.button("Cerrar", on_click=dlg.close).props("flat no-caps")
            ui.image(url).style("width:min(100%,1700px);").props("fit=contain")
        dlg.open()

    async def download_fig(key: str):
        fig = next((f for k, f in a.figures + a.multi_figures if k == key), None)
        if fig is None:
            ui.notify("Este gráfico no está disponible para descargar.", type="warning")
            return
        png = await run.io_bound(fig_to_png, fig, 300)
        ui.download.content(png, f"{_slug(key)}.png", "image/png")

    def results_table(df: pd.DataFrame, fmt="{:.4g}"):
        cols = [{"name": str(c), "label": str(c), "field": str(c), "align": "left", "sortable": True}
                for c in df.columns]
        rows = []
        for _, r in df.iterrows():
            rows.append({str(c): (fmt.format(v) if isinstance(v, float) else str(v)) for c, v in r.items()})
        return ui.table(columns=cols, rows=rows, row_key=str(df.columns[0])) \
            .props("dense flat bordered wrap-cells").classes("w-full")

    def ranking_small() -> pd.DataFrame:
        r = a.ranking_table
        out = pd.DataFrame({"Puesto": range(1, len(r) + 1), "Corrida": [str(i) for i in r.index],
                            "Puntaje compuesto (0-1)": r["Puntaje compuesto (0-1)"].astype(float).values})
        return out

    def transposed(df: pd.DataFrame) -> pd.DataFrame:
        """Una fila por indicador y una columna por corrida (legible con 16+ indicadores)."""
        t = df.set_index(df.columns[0]).T.reset_index()
        t.columns = ["Indicador"] + [str(c) for c in t.columns[1:]]
        return t

    def build_results():
        urls = put_imgs()
        has_val_figs = any(k in a.pngs for k in VALIDATION_FIGURE_KEYS)
        t_val.set_visibility(True)
        t_vfig.set_visibility(has_val_figs)
        t_ext.set_visibility(a.extremes_ran)
        t_rep.set_visibility(True)
        for p in (p_val, p_vfig, p_ext, p_rep):
            p.clear()
        build_validation(urls)
        if has_val_figs:
            build_figure_tabs(p_vfig, [k for k in VALIDATION_FIGURE_KEYS if k in a.pngs], urls)
        if a.extremes_ran:
            build_extremes(urls)
        build_report(urls)
        build_multi_results(urls)

    def build_figure_tabs(parent, keys, urls):
        with parent:
            with ui.tabs().props("align=left dense no-caps inline-label").classes("w-full") as it:
                tt = [ui.tab(k, label=k) for k in keys]
            with ui.tab_panels(it, value=keys[0]).classes("w-full"):
                for k in keys:
                    with ui.tab_panel(k):
                        figure_block(k, urls[k])

    # ---------------------------------------------------------- VALIDACIÓN
    def build_validation(urls):
        keys = [k for k in a.ran_selected if k in a.stats_table.columns]
        with p_val:
            with ui.tabs().props("align=left dense no-caps inline-label").classes("w-full") as it:
                ui.tab("__todos", label="📊 Todos")
                for k in keys:
                    ui.tab(k, label=k)
            with ui.tab_panels(it, value="__todos").classes("w-full"):
                with ui.tab_panel("__todos"):
                    ui.label("Resultados de los métodos elegidos").classes("text-subtitle1 text-weight-bold")
                    ui.label("Cada método tiene su propia pestaña con teoría, fórmula, pasos del cálculo, "
                             "escala de interpretación y el cálculo con tus datos.").classes("ct-muted")
                    results_table(transposed(a.final_table()))
                    if a.ranking_table is not None and len(a.ranking_table):
                        ui.label("Ranking compuesto (0–1, referencia visual)").classes("text-subtitle1 q-mt-md")
                        results_table(ranking_small())
                for k in keys:
                    with ui.tab_panel(k):
                        method_panel(k, urls)

    def method_panel(key: str, urls):
        h = ct_stats.INDICATOR_HELP.get(key, {})
        with ui.row().classes("w-full no-wrap items-start gap-4"):
            with ui.column().classes("gap-3").style("flex:1 1 45%;min-width:0;"):
                ui.label(key).classes("text-h6")
                with ui.card().classes("ct-card w-full"):
                    ui.label("¿Qué es y para qué sirve?").classes("text-subtitle2 text-weight-bold")
                    ui.label(h.get("teoria", "")).classes("ct-pre")
                with ui.card().classes("ct-card w-full"):
                    ui.label("Fórmula").classes("text-subtitle2 text-weight-bold")
                    ui.label(h.get("formula", "")).classes("ct-mono")
                    ui.label(h.get("como_leerlo", "")).classes("ct-pre q-mt-sm")
                with ui.card().classes("ct-card w-full"):
                    ui.label("Pasos del cálculo").classes("text-subtitle2 text-weight-bold")
                    for i, p in enumerate(h.get("pasos", []), 1):
                        ui.label(f"{i}. {p}").classes("ct-pre")
            with ui.column().classes("gap-3").style("flex:1 1 55%;min-width:0;"):
                with ui.card().classes("ct-card w-full"):
                    ui.label("Resultado por corrida").classes("text-subtitle2 text-weight-bold")
                    for run_name, val, q in a.indicator_rows(key):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(run_name).classes("text-body1")
                            col = QUALITY_COLORS.get(q)
                            lab = ui.label(f"{val:.4f}").classes("text-weight-bold text-body1")
                            if col:
                                lab.style(f"color:{col};")
                                ui.label(q).classes("text-caption text-white q-px-sm rounded-borders") \
                                    .style(f"background:{col};")
                    ui.label(ct_stats.scale_description(key)).classes("text-caption ct-muted q-mt-sm")
                    g = urls.get("gauge::" + key)
                    if g:
                        ui.image(g).classes("w-full").props("fit=contain")
                with ui.card().classes("ct-card w-full"):
                    ui.label("Cálculo con los datos de esta corrida (paso a paso)") \
                        .classes("text-subtitle2 text-weight-bold")
                    runs = [str(r) for r in a.stats_table.index]
                    box = ui.column().classes("w-full gap-0")

                    def show(run_name, box=box, key=key):
                        box.clear()
                        with box:
                            for lab, val in a.trace(key, run_name):
                                with ui.row().classes("w-full justify-between no-wrap"):
                                    ui.label(lab)
                                    ui.label(val).classes("text-weight-bold")
                    if len(runs) > 1:
                        ui.select(runs, value=runs[0], label="Corrida",
                                  on_change=lambda e, s=show: s(e.value)).classes("w-64")
                    show(runs[0])

    # -------------------------------------------------------------- EXTREMOS
    def build_extremes(urls):
        with p_ext:
            keys = [k for k in EXTREMES_FIGURE_KEYS if k in a.pngs]
            with ui.tabs().props("align=left dense no-caps inline-label").classes("w-full") as it:
                ui.tab("__res", label="Resultados y parámetros")
                for k in keys:
                    ui.tab(k, label=k)
            with ui.tab_panels(it, value="__res").classes("w-full"):
                with ui.tab_panel("__res"):
                    with ui.expansion("¿Qué es el análisis de extremos (POT)?", value=False) \
                            .classes("w-full ct-card").props("dense"):
                        ui.label("POT (Peaks Over Threshold) selecciona los picos de crecida que superan un "
                                 "umbral (y los mínimos de estiaje bajo otro), garantizando que sean eventos "
                                 "independientes entre sí. Con ellos se calcula el periodo de retorno empírico "
                                 "y se aplica la transformación Box-Cox (a los máximos, y al recíproco 1/caudal "
                                 "en los mínimos) para estabilizar la varianza antes de comparar observado vs. "
                                 "simulado.").classes("ct-pre")
                    for label, pot, bc in (("Máximos (crecidas)", a.pot_max, a.bc_max),
                                           ("Mínimos (estiajes)", a.pot_min, a.bc_min)):
                        with ui.card().classes("ct-card w-full q-mt-sm"):
                            ui.label(label).classes("text-subtitle1 text-weight-bold")
                            if pot is None:
                                ui.label("No se pudo seleccionar ningún evento con los parámetros actuales. "
                                         "Pruebe otro umbral o una separación menor.").classes("text-warning")
                                continue
                            ui.label(f"Eventos seleccionados: {len(pot.obs)}").classes("ct-pre")
                            if bc is not None:
                                try:
                                    ui.label(f"λ de Box-Cox: {bc['lambda']:.4f}")
                                except Exception:
                                    pass
                    for w in a.box_cox_warnings:
                        ui.label(w).classes("text-warning")
                for k in keys:
                    with ui.tab_panel(k):
                        figure_block(k, urls[k])

    # --------------------------------------------------------------- REPORTE
    def build_report(urls):
        with p_rep:
            with ui.row().classes("w-full items-center"):
                ui.label("Reporte completo del análisis").classes("text-h6")
                ui.space()
                ui.label(AUTHOR_CREDIT).classes("text-caption ct-muted")
            # kpis
            with ui.row().classes("gap-3 w-full"):
                n = len(a.df) if a.df is not None else len(a.df_valid)
                best = "—"
                if a.ranking_table is not None and len(a.ranking_table):
                    best = f"{a.ranking_table.index[0]} · {float(a.ranking_table.iloc[0, -1]):.3f}"
                for t, v in (("Filas de datos", str(n)), ("Corridas comparadas", str(len(a.ran_sim_cols))),
                             ("Mejor corrida (puntaje compuesto)", best),
                             ("Extremos (POT)", "Calculados" if a.extremes_ran else "N/D (sin fechas)")):
                    with ui.card().classes("ct-card ct-kpi").style("min-width:200px;"):
                        ui.label(t).classes("text-caption ct-muted")
                        ui.label(v).classes("text-h6")
            # tabla final
            with ui.card().classes("ct-card w-full q-mt-sm"):
                with ui.row().classes("items-center w-full"):
                    ui.label("Tabla final de indicadores (todos los métodos usados)") \
                        .classes("text-subtitle1 text-weight-bold")
                    ui.space()
                    ui.button("📷 Exportar tabla (PNG)", on_click=export_table_png).props("outline dense no-caps")
                results_table(transposed(a.final_table()))
            if a.ranking_table is not None and len(a.ranking_table):
                with ui.card().classes("ct-card w-full"):
                    ui.label("¿Qué serie se ajusta mejor?").classes("text-subtitle1 text-weight-bold")
                    ui.label(f"Puntaje compuesto (0–1) calculado con: {', '.join(a.ranking_indicators)}. "
                             "Es una referencia visual; no reemplaza mirar cada indicador.") \
                        .classes("text-caption ct-muted")
                    results_table(ranking_small())
            # tabla resumen de métodos
            if METHODS_SUMMARY_TITLE in urls:
                with ui.card().classes("ct-card w-full"):
                    figure_block(METHODS_SUMMARY_TITLE, urls[METHODS_SUMMARY_TITLE])
            # exportar
            with ui.card().classes("ct-card w-full"):
                ui.label("Exportar reporte").classes("text-subtitle1 text-weight-bold")
                ui.label("Un formato se descarga con su extensión real (.pdf, .docx, .xlsx); varios formatos "
                         "juntos se entregan en un único .zip.").classes("ct-muted")
                f_pdf = ui.checkbox("PDF", value=True)
                f_docx = ui.checkbox("Word (.docx)")
                f_xlsx = ui.checkbox("Excel (.xlsx)")
                all_keys = [k for k, _ in a.figures + a.multi_figures]
                fig_checks = {}
                with ui.expansion(f"Figuras a incluir ({len(all_keys)})").classes("w-full"):
                    with ui.row().classes("gap-2"):
                        ui.button("Todas", on_click=lambda: [c.set_value(True) for c in fig_checks.values()]) \
                            .props("flat dense no-caps")
                        ui.button("Ninguna", on_click=lambda: [c.set_value(False) for c in fig_checks.values()]) \
                            .props("flat dense no-caps")
                    for k in all_keys:
                        fig_checks[k] = ui.checkbox(k, value=True)

                async def do_export():
                    fm = [f for f, c in (("pdf", f_pdf), ("docx", f_docx), ("xlsx", f_xlsx)) if c.value]
                    if not fm:
                        ui.notify("Elija al menos un formato.", type="warning")
                        return
                    chosen = [k for k, c in fig_checks.items() if c.value]
                    with ui.dialog().props("persistent") as busy, ui.card().classes("items-center q-pa-lg"):
                        ui.spinner(size="xl")
                        ui.label("Generando el reporte…").classes("q-mt-md")
                    busy.open()
                    try:
                        name, data, mime = await run.io_bound(a.export, fm, chosen)
                    except Exception as exc:
                        busy.close()
                        ui.notify(f"Error al exportar: {exc}", type="negative", multi_line=True)
                        return
                    busy.close()
                    ui.download.content(data, name, mime)
                    ui.notify(f"Reporte generado: {name}", type="positive")
                ui.button("⬇ Generar y descargar", on_click=do_export).props("color=primary no-caps unelevated")

    async def export_table_png():
        png = await run.io_bound(a.final_table_transposed_png)
        if png:
            ui.download.content(png, "tabla_indicadores.png", "image/png")

    # --------------------------------------------------------- cambio de letra
    async def on_font(value: str):
        a.chart_font = value
        storage["chart_font"] = value
        if a.stats_table is not None or a.multi_results:
            ui.notify("Letra aplicada: se re-generan los gráficos…", type="info")
            await rerender_all()
        else:
            ui.notify(f"Letra de gráficos: {value}", type="positive")


    # ============================================================ ANÁLISIS MÚLTIPLE
    with p_multi:
        multi_cfg = ui.column().classes("w-full gap-2")
        multi_out = ui.column().classes("w-full gap-2")

    def apply_models(text: str):
        names = []
        for n in (text or "").replace(";", ",").split(","):
            n = n.strip()
            if n and n not in names:
                names.append(n)
        names = names[:8]
        if not names:
            ui.notify("Escriba al menos un nombre de modelo.", type="warning")
            return
        a.multi_models = names
        for v in a.multi_vars:
            v["sims"] = {m: c for m, c in v.get("sims", {}).items() if m in names}
        refresh_multi_config()

    def add_var():
        n = len(a.multi_vars) + 1
        while any(v["name"] == f"Variable {n}" for v in a.multi_vars):
            n += 1
        a.multi_vars.append({"name": f"Variable {n}", "obs": "", "sims": {}})
        refresh_multi_config()

    def remove_var(v):
        if v in a.multi_vars:
            a.multi_vars.remove(v)
        refresh_multi_config()

    def refresh_multi_config():
        multi_cfg.clear()
        if a.raw_df is None:
            return
        cols = [str(c) for c in a.raw_df.columns]
        with multi_cfg:
            with ui.card().classes("ct-card w-full"):
                ui.label("Análisis múltiple: varias variables × varios modelos") \
                    .classes("text-subtitle1 text-weight-bold")
                ui.label("Cada variable (p. ej. un piezómetro, un caudal, una profundidad) tiene su columna "
                         "Observado y, para cada modelo, su columna calculada. Se comparan EF, KGE y PBIAS y se "
                         "obtiene un ranking promedio por modelo. Un modelo sin columna en una variable se omite "
                         "en ella.").classes("text-caption ct-muted")
                with ui.row().classes("items-end gap-2 w-full"):
                    mi = ui.input("Modelos (separados por coma, máx. 8)", value=", ".join(a.multi_models)) \
                        .classes("grow")
                    ui.button("Aplicar modelos", on_click=lambda: apply_models(mi.value)).props("outline no-caps")
                for v in a.multi_vars:
                    with ui.row().classes("items-center gap-2 w-full q-mt-sm"):
                        ui.input("Variable", value=v["name"],
                                 on_change=lambda e, v=v: v.__setitem__("name", e.value or "")).classes("w-44")
                        ui.select(cols, value=v.get("obs") if v.get("obs") in cols else None, label="Observado",
                                  on_change=lambda e, v=v: v.__setitem__("obs", e.value or "")).classes("w-52")
                        for m in a.multi_models:
                            cur = v.get("sims", {}).get(m)
                            ui.select(cols, value=cur if cur in cols else None, label=f"Calculado · {m}",
                                      clearable=True,
                                      on_change=lambda e, v=v, m=m: v.setdefault("sims", {}).__setitem__(
                                          m, e.value or "")).classes("w-52")
                        ui.button(icon="delete", on_click=lambda v=v: remove_var(v)) \
                            .props("flat dense color=negative").tooltip("Quitar variable")
                with ui.row().classes("gap-2 q-mt-sm"):
                    ui.button("+ Variable", on_click=add_var).props("outline no-caps")
                    ui.button("▶ Ejecutar análisis múltiple", on_click=lambda: run_multi_click()) \
                        .props("color=primary no-caps unelevated")

    async def run_multi_click(goto: bool = True):
        with ui.dialog().props("persistent") as busy, ui.card().classes("items-center q-pa-lg"):
            ui.spinner(size="xl")
            ui.label("Calculando el análisis múltiple…").classes("q-mt-md")
        busy.open()
        try:
            await run.io_bound(a.run_multi)
        except Exception as exc:
            busy.close()
            ui.notify(f"Análisis múltiple: {exc}", type="negative", multi_line=True, close_button=True)
            return
        busy.close()
        if a.stats_table is not None:
            build_results()
        else:
            build_multi_results(put_imgs())
        if a.multi_warnings:
            ui.notify("Aviso: " + " | ".join(a.multi_warnings), type="warning", multi_line=True)
        set_status(f"✓ Análisis múltiple listo: {len(a.multi_results)} variable(s) × "
                   f"{len(a.multi_models)} modelo(s).", "ok")
        if goto:
            tabs.set_value("multi")

    def build_multi_results(urls):
        multi_out.clear()
        if not a.multi_results:
            return
        keys = [k for k in MULTI_KEYS if k in urls]
        with multi_out:
            ui.separator()
            with ui.tabs().props("align=left dense no-caps inline-label").classes("w-full") as it:
                for k in keys:
                    ui.tab(k, label=k.replace(" (análisis múltiple)", ""))
                ui.tab("__tab", label="📊 Tablas por variable")
            with ui.tab_panels(it, value=keys[0] if keys else "__tab").classes("w-full"):
                for k in keys:
                    with ui.tab_panel(k):
                        figure_block(k, urls[k])
                        if k == MULTI_KEYS[0]:
                            for ind in ("EF", "KGE"):
                                pv = a.multi_pivots.get(ind)
                                if pv is not None:
                                    ui.label(f"{ind} por variable y modelo").classes("text-subtitle2 q-mt-md")
                                    results_table(pv.reset_index().rename(columns={pv.index.name or "index": "Variable"}),
                                                  "{:.3f}")
                        elif k == MULTI_KEYS[1]:
                            try:
                                pv = ct_stats.pivot_indicator_by_variable(a.multi_results, "PBIAS (%)")
                                results_table(pv.reset_index().rename(columns={pv.index.name or "index": "Variable"}),
                                              "{:.2f}")
                            except Exception:
                                pass
                        elif k == MULTI_KEYS[2] and a.multi_ranking:
                            rk, used = a.multi_ranking
                            ui.label("Puntaje promedio (0–1) con: " + ", ".join(map(str, used))
                                     if used else "").classes("text-caption ct-muted q-mt-sm")
                            t = rk.reset_index()
                            t.columns = ["Modelo"] + [str(c) for c in t.columns[1:]]
                            results_table(t, "{:.3f}")
                with ui.tab_panel("__tab"):
                    for name, tb in a.multi_results.items():
                        ui.label(name).classes("text-subtitle1 text-weight-bold q-mt-sm")
                        t = tb.reset_index()
                        t.columns = ["Modelo"] + [str(c) for c in t.columns[1:]]
                        results_table(transposed(t))

    # ====================================================== tabla vacía y pegado
    def new_table():
        df = pd.DataFrame({"Fecha": pd.date_range("2020-01-01", periods=10).strftime("%Y-%m-%d"),
                           "Observado": [float("nan")] * 10, "Simulado": [float("nan")] * 10})
        load_df(df, "tabla_manual")
        a.date_col, a.obs_col, a.sim_cols = "Fecha", "Observado", ["Simulado"]
        refresh_columns()
        ui.notify("Tabla vacía lista: edítela celda por celda, agregue filas/columnas o pegue datos.",
                  type="info", multi_line=True)

    def paste_dialog():
        with ui.dialog() as dlg, ui.card().style("min-width:min(760px,92vw);"):
            ui.label("Pegar datos").classes("text-h6")
            ui.label("Copie un rango de Excel (o texto separado por tabulador, «;» o «,») y péguelo aquí.") \
                .classes("text-caption ct-muted")
            txt = ui.textarea(placeholder="Fecha\tObservado\tSimulado\n2020-01-01\t1.2\t1.1\n…") \
                .props("outlined autogrow input-style='font-family:monospace;max-height:40vh;overflow:auto'") \
                .classes("w-full")
            hdr = ui.checkbox("La primera fila contiene los nombres de columna", value=True)
            mode = ui.radio({"replace": "Reemplazar la tabla actual", "append": "Agregar al final de la tabla actual"},
                            value="replace").props("dense")

            def ok():
                try:
                    n = a.paste_text(txt.value or "", header=hdr.value,
                                     append=(mode.value == "append" and a.raw_df is not None))
                except Exception as exc:
                    ui.notify(f"No se pudo interpretar el texto: {exc}", type="negative", multi_line=True)
                    return
                dlg.close()
                refresh_columns()
                refresh_grid()
                for t in (t_val, t_vfig, t_ext, t_rep):
                    t.set_visibility(False)
                t_multi.set_visibility(True)
                multi_out.clear()
                refresh_multi_config()
                set_status(f"Datos pegados: {n} filas.", "ok")
                ui.notify(f"{n} filas incorporadas.", type="positive")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancelar", on_click=dlg.close).props("flat no-caps")
                ui.button("Incorporar", on_click=ok).props("color=primary no-caps unelevated")
        dlg.open()

    # ============================================================== PROYECTO
    def save_project():
        try:
            data = a.project_bytes()
        except Exception as exc:
            ui.notify(str(exc), type="warning")
            return
        stem = Path(a.file_name or "proyecto").stem
        ui.download.content(data, f"{stem}.ctproj", "application/json")
        ui.notify("Proyecto guardado (.ctproj).", type="positive")

    def open_project_dialog():
        with ui.dialog() as dlg, ui.card().style("min-width:min(520px,92vw);"):
            ui.label("Abrir proyecto").classes("text-h6")
            ui.label("Suba un archivo .ctproj guardado antes (web o escritorio). Se restauran los datos, "
                     "las columnas, los parámetros y los estilos; luego pulse «Ejecutar».") \
                .classes("text-caption ct-muted")

            async def on_proj(e):
                try:
                    raw = await e.file.read()
                    a.load_project_bytes(raw)
                except Exception as exc:
                    ui.notify(f"No se pudo abrir el proyecto: {exc}", type="negative", multi_line=True)
                    return
                dlg.close()
                storage["chart_font"] = a.chart_font
                sel_font.set_value(a.chart_font)
                for k, ref in pot_refs.items():
                    ref.set_value(getattr(a, k))
                refresh_columns()
                refresh_grid()
                for t in (t_val, t_vfig, t_ext, t_rep):
                    t.set_visibility(False)
                t_multi.set_visibility(True)
                multi_out.clear()
                refresh_multi_config()
                tabs.set_value("datos")
                set_status(f"Proyecto «{a.file_name}» abierto — pulse «Ejecutar análisis».", "ok")
            ui.upload(label="Arrastre aquí el .ctproj", auto_upload=True, on_upload=on_proj,
                      max_file_size=100_000_000).props("accept=.ctproj,.json flat bordered").classes("w-full")
            ui.button("Cancelar", on_click=dlg.close).props("flat no-caps")
        dlg.open()

    # ================================================ estilo de reporte y colores
    async def rerender_all():
        if a.multi_results:
            try:
                await run.io_bound(a.run_multi)
            except Exception as exc:
                ui.notify(f"Análisis múltiple: {exc}", type="warning", multi_line=True)
        if a.stats_table is not None:
            await do_run(goto=False)
        elif a.multi_results:
            build_multi_results(put_imgs())

    def style_dialog():
        from ct_tool.report import REPORT_FONT_CHOICES, REPORT_ALIGN_CHOICES, REPORT_TABLE_STYLE_CHOICES
        al = {"left": "Izquierda", "justify": "Justificado", "center": "Centrado"}
        with ui.dialog() as dlg, ui.card().style("min-width:min(460px,92vw);"):
            ui.label("Estilo del reporte (PDF / Word)").classes("text-h6")
            f = ui.select(list(REPORT_FONT_CHOICES), value=a.report_style.get("font_family"), label="Letra") \
                .classes("w-full")
            g = ui.select({k: al.get(k, k) for k in REPORT_ALIGN_CHOICES},
                          value=a.report_style.get("paragraph_align"), label="Alineación del texto").classes("w-full")
            t = ui.select(list(REPORT_TABLE_STYLE_CHOICES), value=a.report_style.get("table_style"),
                          label="Estilo de tablas").classes("w-full")

            def ok():
                a.report_style = {"font_family": f.value, "paragraph_align": g.value, "table_style": t.value}
                dlg.close()
                ui.notify("Estilo de reporte actualizado (se usa al exportar).", type="positive")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancelar", on_click=dlg.close).props("flat no-caps")
                ui.button("Aplicar", on_click=ok).props("color=primary no-caps unelevated")
        dlg.open()

    def colors_dialog():
        names = a.all_run_names()
        if not names:
            ui.notify("Aún no hay corridas ni modelos: elija columnas simuladas o defina modelos.",
                      type="warning")
            return
        ls_opts = {"-": "Continua ───", "--": "Rayas - - -", "-.": "Raya-punto ─·─", ":": "Puntos ·····"}
        refs = {}
        with ui.dialog() as dlg, ui.card().style("min-width:min(560px,94vw);"):
            ui.label("Colores y líneas por corrida / modelo").classes("text-h6")
            ui.label("Se aplican a todos los gráficos donde aparece cada nombre.").classes("text-caption ct-muted")
            for i, n in enumerate(names):
                cur = a.run_style.get(n, {})
                base = ct_plots._series_style(i)
                with ui.row().classes("items-center gap-3 w-full no-wrap"):
                    ui.label(n).classes("w-40 ellipsis")
                    c = ui.color_input(value=cur.get("color") or base["color"]).classes("w-40")
                    l = ui.select(ls_opts, value=cur.get("linestyle") or base["linestyle"]).classes("w-44")
                    refs[n] = (c, l)

            async def ok():
                a.run_style = {n: {"color": c.value, "linestyle": l.value} for n, (c, l) in refs.items()}
                dlg.close()
                if a.stats_table is not None or a.multi_results:
                    ui.notify("Aplicando colores…", type="info")
                    await rerender_all()

            def reset():
                a.run_style = {}
                dlg.close()
                ui.notify("Colores restablecidos.", type="info")
                ui.timer(0.1, rerender_all, once=True)
            with ui.row().classes("justify-between w-full"):
                ui.button("Restablecer", on_click=reset).props("flat no-caps")
                with ui.row():
                    ui.button("Cancelar", on_click=dlg.close).props("flat no-caps")
                    ui.button("Aplicar", on_click=ok).props("color=primary no-caps unelevated")
        dlg.open()

    ui.label(f"CT 2010 · versión {APP_VERSION} · {AUTHOR_NAME}").classes("text-caption ct-muted q-mt-lg")
