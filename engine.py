"""
Motor de análisis de CT_2010 Web (sin interfaz).

Reúne, en una sola clase independiente de PyQt/NiceGUI, el mismo flujo
que la versión de escritorio: validación con los métodos elegidos,
extremos (POT / Box-Cox) cuando el Eje X son fechas, gráficos con
degradación por gráfico (un gráfico que no se puede generar se omite
del reporte y se explica en pantalla), tablas finales y exportación a
PDF / Word / Excel.
"""
from __future__ import annotations

import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path

import pandas as pd

from ct_tool import io_utils, stats as ct_stats, extremes as ct_extremes, plots as ct_plots
from ct_tool.report import (build_results_pdf, build_results_docx, build_results_xlsx,
                            DEFAULT_REPORT_STYLE, REPORT_FONT_CHOICES, REPORT_ALIGN_CHOICES,
                            REPORT_TABLE_STYLE_CHOICES)

APP_VERSION = "4.1 (Web)"
AUTHOR_NAME = "PhD. Mauricio Villazón"
AUTHOR_CREDIT = f"Metodología original: {AUTHOR_NAME} — K.U.Leuven / UMSS"

VALIDATION_INDICATORS = [
    "MAE", "STD", "RMSE", "EF", "CD", "R", "Model Skill (Willmott)",
    "CR1 (Sesgo del modelo)", "CR4 (NS logarítmico)", "CR5 (NS adaptado)",
    "PBIAS (%)", "KGE", "RSR", "MAE/STD(Oi)",
    "SEE (Auscultación de presas)", "% dentro de ±2·SEE",
]
METHOD_GROUPS = [
    ("Errores absolutos (en las unidades de la variable)", ["MAE", "STD", "RMSE"]),
    ("Eficiencia y correlación", ["EF", "CD", "R", "Model Skill (Willmott)", "KGE", "RSR"]),
    ("Sesgo (¿el modelo sobre o subestima?)", ["CR1 (Sesgo del modelo)", "PBIAS (%)"]),
    ("Caudales bajos y relativos", ["CR4 (NS logarítmico)", "CR5 (NS adaptado)", "MAE/STD(Oi)"]),
    ("Auscultación de presas", ["SEE (Auscultación de presas)", "% dentro de ±2·SEE"]),
]
ESSENTIAL_METHODS = ["MAE", "RMSE", "EF", "R", "KGE", "PBIAS (%)"]
ALWAYS_KEEP_COLUMNS = ["Corrida", "n", "Avg(Oi)", "Avg(Pi)"]
MULTI_KEYS = [
    "Comparación EF y KGE por variable y modelo",
    "Comparación PBIAS por variable y modelo",
    "Ranking promedio por modelo",
    "Dispersión por variable y modelo (análisis múltiple)",
    "Series observadas vs. calculadas por variable (análisis múltiple)",
]
METHODS_SUMMARY_TITLE = "Tabla resumen de métodos de validación utilizados"

VALIDATION_FIGURE_KEYS = [
    "Dispersión (Observado vs. Simulado)", "Comparación (Observado vs. Simulado)",
    "Diagrama de Taylor",
]
EXTREMES_FIGURE_KEYS = [
    "Hidrograma", "Hidrograma (log)", "Caudal acumulado", "Residuos (tiempo)",
    "Residuos vs. Obs", "Curva de duración", "Bisectriz - todos",
    "Bisectriz - máximos", "Extremos máximos", "Box-Cox máximos",
    "Bisectriz - mínimos", "Extremos mínimos", "Box-Cox 1/mínimos", "Selección POT",
]

# matplotlib fija la tipografía al crear cada figura mediante rcParams
# globales: se serializa el cálculo para que dos usuarios con tipografías
# distintas no se pisen.
_RENDER_LOCK = threading.Lock()


def fig_to_png(fig, dpi: int = 130) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    return buf.getvalue()


class Analysis:
    """Estado y lógica de una sesión de usuario."""

    def __init__(self):
        self.raw_df: pd.DataFrame | None = None
        self.file_name: str = ""
        # configuración
        self.date_col = ""
        self.obs_col = ""
        self.sim_cols: list[str] = []
        self.selected = list(VALIDATION_INDICATORS)
        self.see_k = 0
        self.q_max = 0.98
        self.q_min = 0.02
        self.sep = 10
        self.maxev = 150
        self.chart_font = ct_plots.DEFAULT_CHART_FONT
        self.report_style = dict(DEFAULT_REPORT_STYLE)
        self.run_style: dict = {}
        # análisis múltiple
        self.multi_models: list[str] = ["M1", "M2", "M3"]
        self.multi_vars: list[dict] = []     # {"name","obs","sims":{modelo: columna}}
        self.reset_multi()
        self.reset_results()

    def reset_multi(self):
        self.multi_results: dict = {}
        self.multi_data: dict = {}
        self.multi_figures: list[tuple[str, object]] = []
        self.multi_pngs: dict[str, bytes] = {}
        self.multi_ranking = None
        self.multi_warnings: list[str] = []
        self.multi_pivots: dict = {}

    # ---------------------------------------------------------------- datos
    def reset_results(self):
        self.df_valid = None
        self.df = None
        self.extremes_ran = False
        self.pot_max = self.pot_min = None
        self.bc_max = self.bc_min = None
        self.stats_table = None
        self.stats_detail: dict = {}
        self.ranking_table = None
        self.ranking_indicators: list[str] = []
        self.figures: list[tuple[str, object]] = []   # (clave, Figure) -> reporte
        self.pngs: dict[str, bytes] = {}              # clave -> PNG para pantalla
        self.gauge_pngs: dict[str, bytes] = {}
        self.figure_warnings: list[str] = []
        self.box_cox_warnings: list[str] = []
        self.ran_sim_cols: list[str] = []
        self.ran_selected: list[str] = []
        self.note = ""

    def load_dataframe(self, df: pd.DataFrame, name: str):
        self.raw_df = df.reset_index(drop=True)
        self.file_name = name
        cols = [str(c) for c in self.raw_df.columns]
        self.raw_df.columns = cols
        self.reset_results()
        self.reset_multi()
        self.date_col = next((c for c in cols if io_utils.looks_like_date_column(self.raw_df[c])), cols[0])
        numeric = [c for c in cols if c != self.date_col
                   and pd.api.types.is_numeric_dtype(self.raw_df[c])]
        self.obs_col = numeric[0] if numeric else ""
        self.sim_cols = numeric[1:2]
        self.default_multi_vars()

    def default_multi_vars(self):
        """Una variable inicial: el observado elegido y las simuladas, en orden, como M1, M2..."""
        sims = {}
        for i, c in enumerate(self.sim_cols[: len(self.multi_models)]):
            sims[self.multi_models[i]] = c
        self.multi_vars = [{"name": "Variable 1", "obs": self.obs_col, "sims": sims}]

    # ------------------------------------------------- pegar datos (Excel/CSV)
    def paste_text(self, text: str, header: bool = True, append: bool = False) -> int:
        """Interpreta texto pegado (columnas con tabulador, ';' o ',') y lo
        agrega/reemplaza en la tabla. Devuelve las filas incorporadas."""
        text = text.strip("\n\r")
        if not text.strip():
            raise ValueError("No hay texto para pegar.")
        first = text.splitlines()[0]
        sep = "\t" if "\t" in first else (";" if ";" in first else ("," if "," in first else r"\s+"))
        new = pd.read_csv(io.StringIO(text), sep=sep, engine="python", header=0 if header else None)
        if not header:
            new.columns = [f"Col{i + 1}" for i in range(new.shape[1])]
        new.columns = [str(c).strip() for c in new.columns]
        for c in new.columns:
            col = new[c]
            if sep != "," and not pd.api.types.is_numeric_dtype(col):
                col = col.astype(str).str.strip().str.replace(",", ".", regex=False)
            conv = pd.to_numeric(col, errors="coerce")
            if conv.notna().sum() >= 0.9 * max(1, new[c].notna().sum()):
                new[c] = conv
        if append and self.raw_df is not None:
            new = new.reindex(columns=self.raw_df.columns) if set(new.columns) <= set(self.raw_df.columns) \
                else pd.DataFrame(new.values, columns=self.raw_df.columns[: new.shape[1]])
            self.raw_df = pd.concat([self.raw_df, new], ignore_index=True)
            self.reset_results()
        else:
            self.load_dataframe(new, self.file_name or "datos_pegados")
        return len(new)

    def load_path(self, path: str, name: str | None = None):
        self.load_dataframe(io_utils.read_table(path), name or Path(path).name)

    # ------------------------------------------------------------- análisis
    def run(self):
        """Ejecuta validación + (si hay fechas) extremos y gráficos."""
        if self.raw_df is None:
            raise ValueError("Primero cargue un archivo de datos.")
        if not self.obs_col or not self.sim_cols:
            raise ValueError("Elija la columna «Observado» y al menos una serie «Simulado».")
        if not self.selected:
            raise ValueError("Elija al menos un método de validación.")
        with _RENDER_LOCK:
            ct_plots.set_chart_font(self.chart_font)
            self._run_locked()

    def _run_locked(self):
        self.reset_results()
        obs_col, sim_cols = self.obs_col, list(self.sim_cols)
        date_col = self.date_col or None
        self.ran_sim_cols = sim_cols
        self.ran_selected = list(self.selected)

        self.df_valid = io_utils.build_validation_dataset(self.raw_df, obs_col, sim_cols, x_col=date_col)

        ts_df = None
        if date_col and date_col in self.raw_df.columns and \
                io_utils.looks_like_date_column(self.raw_df[date_col]):
            try:
                cand = io_utils.build_timeseries(self.raw_df, date_col, obs_col, sim_cols)
                if cand is not None and not cand.empty and len(cand) >= 2:
                    ts_df = cand
            except Exception:
                ts_df = None
        if ts_df is None:
            self.note = ("Extremos (POT) y gráficos de hidrología omitidos: el «Eje X» no se "
                         "pudo interpretar como fecha.")
        self.df = ts_df
        self.extremes_ran = ts_df is not None

        self._run_stats(ts_df if ts_df is not None else self.df_valid)
        self._render_gauges()

        if ts_df is not None:
            self._run_extremes()
            self._render_all_plots()
        else:
            self._render_validation_plots(self.df_valid)
        self._refresh_methods_summary_figure()

    def _run_stats(self, df):
        table = ct_stats.compare_multiple_runs(df, "Observado", self.ran_sim_cols, k=self.see_k)
        keep = [c for c in table.columns if c in ALWAYS_KEEP_COLUMNS or c in self.ran_selected]
        self.stats_table = table[keep]
        for col in self.ran_sim_cols:
            try:
                full = ct_stats.goodness_of_fit_detailed(df["Observado"], df[col], k=self.see_k)
                self.stats_detail[col] = full.get("_detalle", {})
            except Exception:
                continue
        try:
            self.ranking_table, self.ranking_indicators = ct_stats.rank_runs(self.stats_table)
        except Exception:
            self.ranking_table, self.ranking_indicators = None, []

    def _render_gauges(self):
        base = self.df if self.df is not None else self.df_valid
        obs_mean = float(base["Observado"].mean()) if base is not None else None
        for key in self.ran_selected:
            if key not in self.stats_table.columns:
                continue
            vals = {str(r): float(self.stats_table.loc[r, key]) for r in self.stats_table.index}
            scale = ct_stats.INDICATOR_SCALE.get(key, dict(gauge_type="open_error"))
            try:
                fig = ct_plots.indicator_gauge_plot(key, vals, scale, obs_mean=obs_mean)
                self.gauge_pngs[key] = fig_to_png(fig, 140)
            except Exception:
                pass

    def _run_extremes(self):
        kw = dict(min_separation_days=self.sep, max_events=self.maxev)
        try:
            self.pot_max = ct_extremes.select_pot_events(
                self.df, "Fecha", "Observado", self.ran_sim_cols, kind="max",
                threshold_quantile=self.q_max, **kw)
        except Exception:
            self.pot_max = None
        try:
            self.pot_min = ct_extremes.select_pot_events(
                self.df, "Fecha", "Observado", self.ran_sim_cols, kind="min",
                threshold_quantile=1 - self.q_min, **kw)
        except Exception:
            self.pot_min = None

    def _safe(self, key, fn, *args, **kwargs):
        """Degradación por gráfico: si falla, se explica en pantalla y
        el gráfico NO va al reporte exportado."""
        try:
            fig = fn(*args, **kwargs)
        except Exception as exc:
            self.figure_warnings.append(f"{key}: {exc}")
            self.pngs[key] = fig_to_png(ct_plots.placeholder_message_plot(
                f"Este método no se pudo aplicar con los datos actuales:\n\n{exc}",
                title=f"{key} (no disponible)"), 110)
            return None
        self.figures.append((key, fig))
        self.pngs[key] = fig_to_png(fig)
        return fig

    def _render_validation_plots(self, df):
        if df is None or "Observado" not in df.columns:
            return
        obs = df["Observado"]
        sim = {c: df[c] for c in self.ran_sim_cols if c in df.columns}
        if not sim:
            return
        if "_EjeX" in df.columns and pd.to_numeric(df["_EjeX"], errors="coerce").notna().sum() >= 2:
            x, xl = pd.to_numeric(df["_EjeX"], errors="coerce"), self.date_col or "Eje X"
        elif "_EjeX" in df.columns and pd.to_datetime(df["_EjeX"], errors="coerce").notna().sum() >= 2:
            x, xl = pd.to_datetime(df["_EjeX"], errors="coerce"), self.date_col or "Eje X"
        elif "Fecha" in df.columns:
            x, xl = df["Fecha"], "Fecha"
        else:
            x, xl = pd.Series(range(1, len(df) + 1)), "Número de fila"
        sm = self.run_style
        self._safe(VALIDATION_FIGURE_KEYS[0], ct_plots.bisector_plot, obs, sim,
                   "Dispersión (Observado vs. Simulado) — Validación", unit="", style_map=sm)
        self._safe(VALIDATION_FIGURE_KEYS[1], ct_plots.general_comparison_plot,
                   x, xl, obs, sim, style_map=sm)
        self._safe(VALIDATION_FIGURE_KEYS[2], ct_plots.taylor_diagram_plot, obs, sim, style_map=sm)

    def _render_all_plots(self):
        df, sm, sc = self.df, self.run_style, self.ran_sim_cols
        s = self._safe
        s("Hidrograma", ct_plots.hydrograph_plot, df, "Fecha", "Observado", sc, log_scale=False, style_map=sm)
        s("Hidrograma (log)", ct_plots.hydrograph_plot, df, "Fecha", "Observado", sc, log_scale=True, style_map=sm)
        s("Caudal acumulado", ct_plots.cumulative_discharge_plot, df, "Fecha", "Observado", sc, style_map=sm)
        s("Residuos (tiempo)", ct_plots.residuals_time_plot, df, "Fecha", "Observado", sc, style_map=sm)
        s("Residuos vs. Obs", ct_plots.residuals_vs_observed_plot, df, "Observado", sc, style_map=sm)
        s("Curva de duración", ct_plots.duration_curve_plot, df, "Observado", sc, style_map=sm)
        s("Bisectriz - todos", ct_plots.bisector_plot, df["Observado"], {c: df[c] for c in sc},
          "Dispersión (bisectriz) - todos los datos", style_map=sm)

        if self.pot_max is not None:
            s("Bisectriz - máximos", ct_plots.bisector_plot, self.pot_max.obs, self.pot_max.sim,
              "Dispersión (bisectriz) - máximos POT", style_map=sm)
            s("Extremos máximos", ct_plots.extreme_value_plot, self.pot_max, style_map=sm)
            try:
                self.bc_max = ct_extremes.full_extreme_analysis(self.pot_max)
                s("Box-Cox máximos", ct_plots.extreme_value_plot, self.pot_max,
                  box_cox_values=self.bc_max, style_map=sm)
            except Exception as exc:
                self.box_cox_warnings.append(f"Box-Cox máximos: {exc}")
                self.pngs["Box-Cox máximos"] = fig_to_png(ct_plots.placeholder_message_plot(
                    f"No se pudo calcular Box-Cox de los máximos:\n\n{exc}",
                    title="Box-Cox - máximos (no disponible)"), 110)
        if self.pot_min is not None:
            s("Bisectriz - mínimos", ct_plots.bisector_plot, self.pot_min.obs, self.pot_min.sim,
              "Dispersión (bisectriz) - mínimos POT", style_map=sm)
            s("Extremos mínimos", ct_plots.extreme_value_plot, self.pot_min, style_map=sm)
            try:
                self.bc_min = ct_extremes.full_extreme_analysis(self.pot_min)
                s("Box-Cox 1/mínimos", ct_plots.extreme_value_plot, self.pot_min,
                  box_cox_values=self.bc_min, ylabel="1/Caudal", style_map=sm)
            except Exception as exc:
                self.box_cox_warnings.append(f"Box-Cox 1/mínimos: {exc}")
                self.pngs["Box-Cox 1/mínimos"] = fig_to_png(ct_plots.placeholder_message_plot(
                    f"No se pudo calcular Box-Cox de los mínimos:\n\n{exc}",
                    title="Box-Cox - 1/mínimos (no disponible)"), 110)
        s("Selección POT", ct_plots.pot_selection_plot, df, "Fecha", "Observado", self.pot_max, self.pot_min)
        self._render_validation_plots(df)

    def _refresh_methods_summary_figure(self):
        if not self.ran_selected:
            return
        try:
            dfm = ct_stats.methods_summary_table(self.ran_selected)
            fig = ct_plots.styled_table_figure(
                dfm, title=METHODS_SUMMARY_TITLE,
                col_wrap_widths={"Indicador": 16, "Qué mide": 24, "Fórmula": 26,
                                 "Rango / Óptimo": 16, "Referencia": 18},
                font_family=None)
        except Exception as exc:
            self.figure_warnings.append(f"{METHODS_SUMMARY_TITLE}: {exc}")
            return
        self.figures.append((METHODS_SUMMARY_TITLE, fig))
        self.pngs[METHODS_SUMMARY_TITLE] = fig_to_png(fig)

    # ------------------------------------------------------ análisis múltiple
    def run_multi(self):
        with _RENDER_LOCK:
            ct_plots.set_chart_font(self.chart_font)
            self._run_multi_locked()

    def _run_multi_locked(self):
        if self.raw_df is None:
            raise ValueError("Primero cargue o introduzca datos.")
        defs = []
        for v in self.multi_vars:
            obs = v.get("obs")
            sims = {m: c for m, c in (v.get("sims") or {}).items() if c and c != obs}
            if obs and sims:
                nm = (v.get("name") or "Variable").strip() or "Variable"
                base, k = nm, 2
                while any(d[0] == nm for d in defs):
                    nm, k = f"{base} ({k})", k + 1
                defs.append((nm, obs, sims))
        if not defs:
            raise ValueError("Defina al menos una variable con columna Observado y un modelo con "
                             "columna Simulado.")
        self.reset_multi()
        shared_x = self.date_col or None
        if shared_x:
            own = {o for _, o, _ in defs}
            for _, _, sm in defs:
                own.update(sm.values())
            if shared_x in own:
                shared_x = None
        warns = []
        for name, obs_col, sim_map in defs:
            try:
                dfv = io_utils.build_validation_dataset(self.raw_df, obs_col, list(sim_map.values()),
                                                        x_col=shared_x)
                table = ct_stats.compare_multiple_runs(dfv, "Observado", list(sim_map.values()), k=self.see_k)
                inv = {c: m for m, c in sim_map.items()}
                table.index = [inv.get(ix, ix) for ix in table.index]
                self.multi_results[name] = table
                self.multi_data[name] = {
                    "obs": dfv["Observado"],
                    "sim": {m: dfv[c] for m, c in sim_map.items() if c in dfv.columns},
                    "x": dfv["_EjeX"] if "_EjeX" in dfv.columns else None}
            except Exception as exc:
                warns.append(f"{name}: {exc}")
        if not self.multi_results:
            raise ValueError("No se pudo calcular ninguna variable:\n" + "\n".join(warns))

        sm_ = self.run_style
        order = list(self.multi_models)

        def add(key, fn, *a, **k):
            try:
                fig = fn(*a, **k)
            except Exception as exc:
                warns.append(f"{key}: {exc}")
                self.multi_pngs[key] = fig_to_png(ct_plots.placeholder_message_plot(
                    f"Este gráfico no se pudo generar con los datos actuales:\n\n{exc}",
                    title=f"{key} (no disponible)"), 110)
                return None
            self.multi_figures.append((key, fig))
            self.multi_pngs[key] = fig_to_png(fig)
            return fig

        try:
            ef = ct_stats.pivot_indicator_by_variable(self.multi_results, "EF")
            kge = ct_stats.pivot_indicator_by_variable(self.multi_results, "KGE")
            add(MULTI_KEYS[0], ct_plots.ef_kge_comparison_plot, ef, kge, style_map=sm_)
            self.multi_pivots = {"EF": ef, "KGE": kge}
        except Exception as exc:
            warns.append(f"{MULTI_KEYS[0]}: {exc}")
        try:
            pb = ct_stats.pivot_indicator_by_variable(self.multi_results, "PBIAS (%)")
            add(MULTI_KEYS[1], ct_plots.pbias_comparison_plot, pb, style_map=sm_)
        except Exception as exc:
            warns.append(f"{MULTI_KEYS[1]}: {exc}")
        try:
            rk, used = ct_stats.average_ranking_by_model(self.multi_results)
            self.multi_ranking = (rk, used)
            add(MULTI_KEYS[2], ct_plots.average_ranking_plot, rk)
        except Exception as exc:
            warns.append(f"{MULTI_KEYS[2]}: {exc}")
        add(MULTI_KEYS[3], ct_plots.multi_variable_dispersion_grid_plot,
            {n: (d["obs"], d["sim"]) for n, d in self.multi_data.items()},
            model_order=order, style_map=sm_)
        ts = {}
        for n, d in self.multi_data.items():
            x = d["x"]
            if x is not None and pd.to_numeric(x, errors="coerce").notna().sum() >= 2:
                xv = pd.to_numeric(x, errors="coerce")
            elif x is not None and pd.to_datetime(x, errors="coerce").notna().sum() >= 2:
                xv = pd.to_datetime(x, errors="coerce")
            else:
                xv = pd.Series(range(1, len(d["obs"]) + 1))
            ts[n] = (xv, d["obs"], d["sim"])
        add(MULTI_KEYS[4], ct_plots.multi_variable_timeseries_grid_plot, ts,
            x_label=shared_x or "Número de fila", model_order=order, style_map=sm_)
        self.multi_warnings = warns

    def multi_ranking_table(self):
        if not self.multi_ranking:
            return pd.DataFrame()
        return self.multi_ranking[0].reset_index()

    # ------------------------------------------------------------- proyecto
    def project_bytes(self) -> bytes:
        if self.raw_df is None:
            raise ValueError("Primero cargue un archivo de datos.")
        payload = {
            "version": 2, "app": "CT_2010_Web", "file_name": self.file_name,
            "date_col": self.date_col, "obs_col": self.obs_col, "sim_cols": list(self.sim_cols),
            "params": {"q_max": self.q_max, "q_min": self.q_min, "sep": self.sep, "maxev": self.maxev,
                       "see_k": self.see_k, "selected_indicators": self.selected,
                       "chart_font": self.chart_font, "report_style": self.report_style,
                       "run_style": self.run_style, "multi_models": self.multi_models,
                       "multi_vars": self.multi_vars},
            "data": json.loads(self.raw_df.to_json(orient="split", date_format="iso")),
        }
        return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")

    def load_project_bytes(self, raw: bytes):
        payload = json.loads(raw.decode("utf-8"))
        df = pd.read_json(io.StringIO(json.dumps(payload["data"])), orient="split")
        self.load_dataframe(df, payload.get("file_name") or "proyecto")
        self.date_col = payload.get("date_col", self.date_col)
        self.obs_col = payload.get("obs_col", self.obs_col)
        self.sim_cols = list(payload.get("sim_cols", self.sim_cols))
        p = payload.get("params", {})
        self.q_max = p.get("q_max", self.q_max); self.q_min = p.get("q_min", self.q_min)
        self.sep = p.get("sep", self.sep); self.maxev = p.get("maxev", self.maxev)
        self.see_k = p.get("see_k", 0)
        self.selected = [k for k in p.get("selected_indicators", self.selected) if k in VALIDATION_INDICATORS] \
            or list(VALIDATION_INDICATORS)
        self.chart_font = p.get("chart_font", self.chart_font)
        self.report_style = {**DEFAULT_REPORT_STYLE, **p.get("report_style", {})}
        self.run_style = p.get("run_style", {}) or {}
        self.multi_models = p.get("multi_models", self.multi_models)
        self.multi_vars = p.get("multi_vars", self.multi_vars)

    def all_run_names(self) -> list[str]:
        names = []
        for n in list(self.sim_cols) + list(self.multi_models):
            if n not in names:
                names.append(n)
        return names

    # ------------------------------------------------------------- consultas
    def indicator_rows(self, key: str) -> list[tuple[str, float, str | None]]:
        """[(corrida, valor, calidad|None)] de un indicador."""
        if self.stats_table is None or key not in self.stats_table.columns:
            return []
        return [(str(r), float(self.stats_table.loc[r, key]),
                 ct_stats.quality_label(key, self.stats_table.loc[r, key]))
                for r in self.stats_table.index]

    def trace(self, key: str, run: str):
        det = self.stats_detail.get(run)
        if not det or self.stats_table is None or key not in self.stats_table.columns:
            return []
        return ct_stats.calculation_trace(key, det, self.stats_table.loc[run, key])

    def final_table(self) -> pd.DataFrame:
        if self.stats_table is None:
            return pd.DataFrame()
        return self.stats_table.reset_index()

    def final_table_transposed_png(self) -> bytes | None:
        df = self.final_table()
        if df.empty:
            return None

        def _fmt(v):
            return f"{v:.4g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
        t = df.set_index(df.columns[0]).T.reset_index()
        t.columns = ["Indicador"] + [str(c) for c in t.columns[1:]]
        for c in t.columns[1:]:
            t[c] = t[c].map(_fmt)
        with _RENDER_LOCK:
            ct_plots.set_chart_font(self.chart_font)
            fig = ct_plots.styled_table_figure(t, title="Indicadores de validación por modelo")
            return fig_to_png(fig, 300)

    def export_params(self) -> dict:
        n = len(self.df) if self.df is not None else (len(self.df_valid) if self.df_valid is not None else 0)
        p = {"Archivo": self.file_name or "-", "N° de datos": n,
             "k (parámetros calibrados, SEE)": self.see_k}
        if self.extremes_ran:
            p.update({"Cuantil umbral máximos": self.q_max, "Cuantil umbral mínimos": self.q_min,
                      "Separación mínima [días]": self.sep})
        else:
            p["Extremos (POT) / gráficos"] = "no ejecutado en esta corrida"
        return p

    # ----------------------------------------------------------- exportación
    def export(self, formats: list[str], figure_keys: list[str] | None = None,
               indicators: list[str] | None = None) -> tuple[str, bytes, str]:
        """Genera el reporte; devuelve (nombre, bytes, mime). Un formato
        -> archivo con su extensión real; varios -> un .zip."""
        if self.stats_table is None:
            raise ValueError("Ejecute primero el análisis.")
        builders = {"pdf": (build_results_pdf, ".pdf", "application/pdf"),
                    "docx": (build_results_docx, ".docx",
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                    "xlsx": (build_results_xlsx, ".xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        figs = [(k, f) for k, f in self.figures + self.multi_figures
                if figure_keys is None or k in figure_keys]
        table = self.final_table()
        if indicators is not None:
            table = table[[c for c in table.columns if c in ALWAYS_KEEP_COLUMNS or c in indicators]]
        ranking = ((self.ranking_table, self.ranking_indicators)
                   if self.ranking_table is not None else None)
        stem = (Path(self.file_name).stem if self.file_name else "reporte") + "_reporte_CT"
        params = self.export_params()
        outputs = []
        with _RENDER_LOCK, tempfile.TemporaryDirectory() as tmp:
            ct_plots.set_chart_font(self.chart_font)
            for fmt in formats:
                builder, ext, mime = builders[fmt]
                path = str(Path(tmp) / f"{stem}{ext}")
                builder(path, self.file_name or "datos", table, figs, params, ranking=ranking,
                        multi_ranking=self.multi_ranking, calc_detail=self.stats_detail, style=self.report_style)
                outputs.append((f"{stem}{ext}", Path(path).read_bytes(), mime))
        if len(outputs) == 1:
            return outputs[0]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data, _ in outputs:
                zf.writestr(name, data)
        return f"{stem}.zip", buf.getvalue(), "application/zip"
