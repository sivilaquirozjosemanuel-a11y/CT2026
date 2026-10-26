"""
plots.py
--------
Generadores de gráficos de diagnóstico, replicando el "Menú de
gráficos" de la hoja "Bissector" de CT_2010.xlsm (14 gráficos):

  1. Caudal en el tiempo - escala lineal
  2. Caudal en el tiempo - escala logarítmica
  3. Caudal acumulado
  4. Residuos (Simulado - Observado) en el tiempo
  5. Caudal ordenado (curva de duración / "rank discharge")
  6. Residuos vs. observado
  7. Dispersión (bisectriz) - todos los datos
  8. Dispersión (bisectriz) - máximos POT
  9. Dispersión (bisectriz) - mínimos POT
  10. Selección de eventos POT sobre el hidrograma
  11. Valores extremos máximos (periodo de retorno)
  12. Valores extremos mínimos (periodo de retorno)
  13. Box-Cox - máximos
  14. Box-Cox - 1/mínimos

Todas las funciones devuelven un objeto `matplotlib.figure.Figure`
(no llaman a `plt.show()`), para poder incrustarlas en la interfaz
Tkinter o guardarlas a archivo/PDF/Word/Excel indistintamente.

Estilo visual
-------------
Las figuras siguen una línea de "calidad de artículo científico"
(tipografía limpia, paleta apta para daltonismo y para impresión en
blanco y negro, ejes sin marco superior/derecho, grilla discreta):
ver `apply_journal_style()` más abajo, que se aplica una sola vez al
importar este módulo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # backend no interactivo por defecto; la GUI cambia a TkAgg
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from .extremes import POTResult

# ---------------------------------------------------------------------------
# Estilo "calidad revista Q1": tipografía limpia, paleta apta para
# daltonismo (Okabe & Ito, 2008) y para impresión en blanco y negro
# (colores + estilos de línea/marcador distintos), ejes sin marco
# superior/derecho, grilla discreta. Se aplica una sola vez al importar
# el módulo, para que TODAS las figuras (GUI, PDF, Word, Excel) salgan
# con el mismo aspecto profesional sin repetir código en cada función.
# ---------------------------------------------------------------------------

# Paleta Okabe-Ito: distinguible tanto en color como en escala de grises,
# la más recomendada en revistas científicas para lectores con daltonismo.
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442"]
# Estilos de línea que se combinan con el color, para que las series sigan
# siendo distinguibles si el reporte se imprime en blanco y negro.
LINESTYLES = ["-", "--", "-.", ":"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X"]

OBS_COLOR = "#1A1A1A"  # casi negro, para la serie observada (referencia)


# ---------------------------------------------------------------------------
# Tipo de letra de TODOS los gráficos (elegible por la usuaria)
# ---------------------------------------------------------------------------
# Tipografías "de siempre" que se ofrecen primero en el selector, con sus
# equivalentes métricos libres (Liberation/Carlito/Caladea) por si el
# sistema no tiene la original (p. ej. Linux/LibreOffice). En Windows se
# usa directamente la original.
CHART_FONT_PRESETS = ["Arial", "Times New Roman", "Calibri", "Cambria",
                      "Helvetica", "Georgia", "Verdana", "Tahoma", "Segoe UI",
                      "Courier New", "DejaVu Sans"]
_FONT_EQUIVALENTS = {
    "Arial": ["Liberation Sans", "Arimo", "Helvetica"],
    "Helvetica": ["Arial", "Liberation Sans", "Arimo"],
    "Times New Roman": ["Liberation Serif", "Tinos", "DejaVu Serif"],
    "Calibri": ["Carlito"],
    "Cambria": ["Caladea"],
    "Courier New": ["Liberation Mono", "Cousine", "DejaVu Sans Mono"],
    "Georgia": ["DejaVu Serif"],
    "Verdana": ["DejaVu Sans"],
    "Tahoma": ["DejaVu Sans"],
    "Segoe UI": ["Inter", "DejaVu Sans"],
}
DEFAULT_CHART_FONT = "Arial"
_chart_font = {"family": DEFAULT_CHART_FONT}


def installed_font_families() -> list[str]:
    """Familias tipográficas que matplotlib puede dibujar en este
    equipo (ordenadas, sin duplicados)."""
    from matplotlib import font_manager
    return sorted({f.name for f in font_manager.fontManager.ttflist})


def available_chart_fonts() -> list[str]:
    """Lista para el selector de la GUI: primero las tipografías
    habituales de reporte (si están instaladas o tienen equivalente),
    luego el resto de las instaladas en el equipo."""
    installed = set(installed_font_families())
    presets = [p for p in CHART_FONT_PRESETS
               if p in installed or any(e in installed for e in _FONT_EQUIVALENTS.get(p, []))]
    rest = [f for f in sorted(installed) if f not in presets]
    return presets + rest


def _resolve_chart_font(family: str | None) -> list[str]:
    """Lista de familias para `font.family` (matplotlib prueba en orden
    y cae al siguiente si falta algún símbolo): la elegida, sus
    equivalentes métricos, y DejaVu Sans al final como respaldo."""
    installed = set(installed_font_families())
    chain: list[str] = []
    name = family or DEFAULT_CHART_FONT
    for cand in [name] + _FONT_EQUIVALENTS.get(name, []):
        if cand in installed and cand not in chain:
            chain.append(cand)
    if "DejaVu Sans" not in chain:
        chain.append("DejaVu Sans")
    return chain


def get_chart_font() -> str:
    return _chart_font["family"]


def set_chart_font(family: str | None) -> str:
    """Cambia el tipo de letra de todos los gráficos que se dibujen a
    partir de ahora (las figuras ya creadas hay que regenerarlas).
    Devuelve el nombre efectivamente aplicado."""
    _chart_font["family"] = family or DEFAULT_CHART_FONT
    apply_journal_style()
    return _chart_font["family"]


def apply_journal_style() -> None:
    plt.rcParams.update({
        "font.family": _resolve_chart_font(_chart_font["family"]),
        "font.size": 10,
        "axes.titlesize": 11.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 10.5,
        "axes.labelweight": "bold",
        "axes.edgecolor": "#3A3A3A",
        "axes.linewidth": 0.9,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "#B0B0B0",
        "grid.alpha": 0.35,
        "grid.linewidth": 0.6,
        "grid.linestyle": "--",
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.color": "#3A3A3A",
        "ytick.color": "#3A3A3A",
        "legend.fontsize": 8.5,
        "legend.frameon": True,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "#CCCCCC",
        "legend.fancybox": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 300,
        "lines.linewidth": 1.3,
        "lines.markersize": 4.5,
    })


apply_journal_style()


def _new_fig(figsize=(7.5, 4.3)):
    fig = plt.Figure(figsize=figsize, dpi=140, constrained_layout=True)
    ax = fig.add_subplot(111)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return fig, ax


def _style_legend(ax, ncol=1):
    leg = ax.legend(ncol=ncol, loc="best")
    if leg is not None:
        leg.get_frame().set_linewidth(0.6)


def _series_style(i):
    """Color + estilo de línea/marcador consistentes para la i-ésima
    corrida simulada, distinguibles también en blanco y negro."""
    return dict(color=COLORS[i % len(COLORS)],
                linestyle=LINESTYLES[i % len(LINESTYLES)],
                marker=MARKERS[i % len(MARKERS)])


LINESTYLE_CHOICES = ["-", "--", "-.", ":"]
MARKER_CHOICES = ["o", "s", "^", "D", "v", "P", "X"]


def _resolve_style(name: str, i: int, style_map: dict | None = None) -> dict:
    """Estilo (color/línea/marcador) para la serie `name` (nombre de
    columna simulada o de modelo): si la usuaria definió un color y/o
    tipo de línea propios para ese nombre (diálogo "Colores y líneas" de
    la GUI, guardado en `style_map` como {nombre: {"color":..,
    "linestyle":..}}), se usan esos; si no, se cae al estilo por índice
    de siempre (`_series_style`) -- esta función es un reemplazo
    "drop-in" de `_series_style(i)` que no cambia nada cuando
    `style_map` es `None` o no trae esa clave."""
    base = _series_style(i)
    custom = (style_map or {}).get(name)
    if custom:
        if custom.get("color"):
            base = dict(base, color=custom["color"])
        if custom.get("linestyle"):
            base = dict(base, linestyle=custom["linestyle"])
    return base


def hydrograph_plot(df: pd.DataFrame, date_col: str, obs_col: str,
                     sim_cols: list[str], log_scale: bool = False,
                     style_map: dict | None = None) -> plt.Figure:
    fig, ax = _new_fig()
    ax.plot(df[date_col], df[obs_col], color=OBS_COLOR, lw=1.4, label=obs_col, zorder=3)
    for i, c in enumerate(sim_cols):
        st = _resolve_style(c, i, style_map)
        ax.plot(df[date_col], df[c], color=st["color"], ls=st["linestyle"], lw=1.1,
                 alpha=0.9, label=c)
    if log_scale:
        ax.set_yscale("log")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Caudal [m³/s]")
    ax.set_title("Hidrograma observado vs. simulado" + (" (escala log)" if log_scale else ""))
    _style_legend(ax)
    fig.autofmt_xdate(rotation=20, ha="right")
    return fig


def cumulative_discharge_plot(df: pd.DataFrame, date_col: str, obs_col: str,
                               sim_cols: list[str], style_map: dict | None = None) -> plt.Figure:
    fig, ax = _new_fig()
    ax.plot(df[date_col], df[obs_col].cumsum(), color=OBS_COLOR, lw=1.6, label=obs_col, zorder=3)
    for i, c in enumerate(sim_cols):
        st = _resolve_style(c, i, style_map)
        ax.plot(df[date_col], df[c].cumsum(), color=st["color"], ls=st["linestyle"], lw=1.2,
                 label=c)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Caudal acumulado [m³/s]")
    ax.set_title("Caudal acumulado (curva de masa)")
    _style_legend(ax)
    fig.autofmt_xdate(rotation=20, ha="right")
    return fig


def residuals_time_plot(df: pd.DataFrame, date_col: str, obs_col: str,
                         sim_cols: list[str], style_map: dict | None = None) -> plt.Figure:
    fig, ax = _new_fig()
    for i, c in enumerate(sim_cols):
        st = _resolve_style(c, i, style_map)
        resid = df[c] - df[obs_col]
        ax.plot(df[date_col], resid, color=st["color"], ls=st["linestyle"], lw=0.9, label=c)
    ax.axhline(0, color=OBS_COLOR, lw=1.0, zorder=3)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Simulado − Observado [m³/s]")
    ax.set_title("Residuos en el tiempo")
    _style_legend(ax)
    fig.autofmt_xdate(rotation=20, ha="right")
    return fig


def residuals_vs_observed_plot(df: pd.DataFrame, obs_col: str,
                                sim_cols: list[str], style_map: dict | None = None) -> plt.Figure:
    fig, ax = _new_fig()
    for i, c in enumerate(sim_cols):
        st = _resolve_style(c, i, style_map)
        resid = df[c] - df[obs_col]
        ax.scatter(df[obs_col], resid, s=14, marker=st["marker"], color=st["color"],
                    alpha=0.55, linewidths=0, label=c)
    ax.axhline(0, color=OBS_COLOR, lw=1.0, zorder=3)
    ax.set_xlabel("Observado [m³/s]")
    ax.set_ylabel("Simulado − Observado [m³/s]")
    ax.set_title("Residuos vs. observado")
    _style_legend(ax)
    return fig


def duration_curve_plot(df: pd.DataFrame, obs_col: str, sim_cols: list[str],
                         log_scale: bool = True, style_map: dict | None = None) -> plt.Figure:
    """Curva de duración de caudales (caudal ordenado de mayor a
    menor vs. probabilidad de excedencia), equivalente a "Rank
    discharge" en el menú de gráficos original."""
    fig, ax = _new_fig()
    n = len(df)
    prob = (np.arange(1, n + 1) / (n + 1)) * 100  # posición de graficación Weibull

    obs_sorted = np.sort(df[obs_col].to_numpy())[::-1]
    ax.plot(prob, obs_sorted, color=OBS_COLOR, lw=1.6, label=obs_col, zorder=3)
    for i, c in enumerate(sim_cols):
        st = _resolve_style(c, i, style_map)
        sim_sorted = np.sort(df[c].to_numpy())[::-1]
        ax.plot(prob, sim_sorted, color=st["color"], ls=st["linestyle"], lw=1.2, label=c)
    if log_scale:
        ax.set_yscale("log")
    ax.set_xlabel("Probabilidad de excedencia [%]")
    ax.set_ylabel("Caudal [m³/s]")
    ax.set_title("Curva de duración de caudales")
    _style_legend(ax)
    ax.grid(which="minor", alpha=0.15, linestyle=":")
    return fig


def bisector_plot(obs, sim_dict: dict, title: str = "Dispersión (bisectriz)",
                   unit: str = "m³/s", style_map: dict | None = None) -> plt.Figure:
    """Gráfico de dispersión observado vs. simulado con la línea de
    identidad 1:1 (bisectriz), equivalente a los gráficos "Bissector"
    del Excel para todos los datos / solo máximos / solo mínimos.
    `unit` se agrega entre corchetes a los ejes (p. ej. "m³/s" para
    caudal); se puede dejar vacío para datos genéricos (geotecnia,
    estructuras, etc.) donde no aplica una unidad fija de caudal.

    La leyenda va FUERA del área de datos (a la derecha), no encima:
    con muchas corridas simuladas, una leyenda "loc='best'" adentro del
    cuadrado 1:1 terminaba tapando puntos, y el ancho extra reservado a
    la derecha evita eso sin importar cuántas corridas se comparen."""
    obs = np.asarray(obs, dtype=float)
    if np.nanstd(obs) == 0 or len(obs) < 2:
        raise ValueError(
            "No se puede graficar la dispersión: el observado no tiene variación "
            "(todos los valores son iguales) o hay menos de 2 datos.")
    fig = plt.Figure(figsize=(7.6, 5.8), dpi=140)
    ax = fig.add_axes([0.11, 0.11, 0.56, 0.82])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    all_vals = [obs]
    for i, (name, sim) in enumerate(sim_dict.items()):
        sim = np.asarray(sim, dtype=float)
        all_vals.append(sim)
        st = _resolve_style(name, i, style_map)
        ax.scatter(obs, sim, s=20, alpha=0.6, marker=st["marker"], color=st["color"],
                    linewidths=0, label=name)
    lo = min(v.min() for v in all_vals)
    hi = max(v.max() for v in all_vals)
    ax.plot([lo, hi], [lo, hi], color=OBS_COLOR, lw=1.1, ls="--", label="Bisectriz 1:1", zorder=1)
    suffix = f" [{unit}]" if unit else ""
    ax.set_xlabel(f"Observado{suffix}")
    ax.set_ylabel(f"Simulado{suffix}")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.06, 0.5), fontsize=8.5, framealpha=0.9)
    if leg is not None:
        leg.get_frame().set_linewidth(0.6)
    return fig


def general_comparison_plot(x, x_label: str, obs, sim_dict: dict,
                             y_label: str = "Valor",
                             title: str = "Observado vs. simulado",
                             style_map: dict | None = None) -> plt.Figure:
    """Gráfico de línea genérico Observado/Simulado(s) contra el "Eje
    X" que la usuaria haya elegido (fecha, profundidad, distancia,
    número de ensayo...) o, si no eligió ninguno, contra el número de
    fila. A diferencia de `hydrograph_plot` (que exige fecha real),
    este funciona con cualquier par observado/simulado -- es el
    gráfico que acompaña a la pestaña "Validación" cuando se usa la
    herramienta para datos que no son series de tiempo hidrológicas
    (p. ej. profundidad vs. asentamiento en geotecnia)."""
    obs = np.asarray(obs, dtype=float)
    x = np.asarray(x)
    if len(obs) < 2:
        raise ValueError("Se necesitan al menos 2 datos para graficar.")
    # Si el eje X es numérico o una fecha, se ordena para que la línea
    # no "vuelva atrás" visualmente; si no (p.ej. texto/categorías), se
    # deja en el orden original.
    order = np.arange(len(obs))
    if np.issubdtype(x.dtype, np.number) or np.issubdtype(x.dtype, np.datetime64):
        order = np.argsort(x)
    fig, ax = _new_fig()
    marker_obs = "o" if len(obs) <= 60 else None
    ax.plot(x[order], obs[order], color=OBS_COLOR, lw=1.3, marker=marker_obs, markersize=3.5,
             label="Observado", zorder=3)
    for i, (name, sim) in enumerate(sim_dict.items()):
        sim = np.asarray(sim, dtype=float)
        st = _resolve_style(name, i, style_map)
        marker_sim = st["marker"] if len(obs) <= 60 else None
        ax.plot(x[order], sim[order], color=st["color"], ls=st["linestyle"], lw=1.1,
                 marker=marker_sim, markersize=3.2, alpha=0.9, label=name)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    _style_legend(ax)
    if np.issubdtype(x.dtype, np.datetime64):
        fig.autofmt_xdate(rotation=20, ha="right")
    return fig


def taylor_diagram_plot(obs, sim_dict: dict,
                         title: str = "Diagrama de Taylor",
                         style_map: dict | None = None) -> plt.Figure:
    """Diagrama de Taylor (Taylor, 2001): resume en un solo gráfico
    polar tres indicadores a la vez -- la correlación (ángulo), la
    desviación estándar normalizada respecto a la observada (radio) y
    el RMSE centrado (distancia al punto de referencia "Observado",
    mostrado como arcos concéntricos) -- para comparar de un vistazo
    varias corridas simuladas. Es la respuesta gráfica "clásica" a la
    pregunta de si R/CD/RMSE se pueden representar en un gráfico: acá
    los tres a la vez, en vez de mirarlos por separado."""
    obs = np.asarray(obs, dtype=float)
    std_obs = float(np.nanstd(obs))
    if std_obs == 0 or len(obs) < 2:
        raise ValueError(
            "No se puede construir el diagrama de Taylor: el observado no tiene "
            "variación (desviación estándar cero) o hay menos de 2 datos.")

    points = []  # (nombre, r_norm, corr)
    for name, sim in sim_dict.items():
        sim = np.asarray(sim, dtype=float)
        mask = ~np.isnan(obs) & ~np.isnan(sim)
        if mask.sum() < 2 or np.nanstd(sim[mask]) == 0:
            continue
        r_norm = float(np.std(sim[mask])) / std_obs
        corr = float(np.corrcoef(obs[mask], sim[mask])[0, 1])
        points.append((name, r_norm, corr))
    if not points:
        raise ValueError(
            "No se pudo calcular el diagrama de Taylor para ninguna corrida (datos "
            "insuficientes o sin variación).")

    max_r = max([1.35] + [p[1] * 1.2 for p in points])

    # Sin constrained_layout: con ese modo activado, el texto rotado del
    # eje de correlación (colocado bien afuera del arco, en coordenadas
    # de datos) obligaba al motor de layout a encoger todo el gráfico
    # para que ese texto entrara en el lienzo -- el síntoma reportado
    # era un cuadrante minúsculo con mucho espacio en blanco alrededor.
    # Se arma el layout a mano en su lugar: eje cuadrado a la izquierda
    # y una franja fija a la derecha para la leyenda, que además queda
    # AFUERA del cuadrante (nunca superpuesta a las líneas/etiquetas de
    # la grilla, sin importar cuántas corridas se comparen).
    fig = plt.Figure(figsize=(8.6, 6.2), dpi=140)
    # bottom=0.19 (en vez de 0.10) para dejar sitio abajo a la barra de
    # color horizontal del mapa de calor + su etiqueta, sin que se
    # recorte contra el borde del lienzo (esta figura se muestra tal
    # cual en la GUI, sin recorte automático tipo `bbox_inches="tight"`).
    ax = fig.add_axes([0.10, 0.19, 0.62, 0.69], polar=True)
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_thetamin(0)
    ax.set_thetamax(90)
    ax.set_ylim(0, max_r)
    ax.set_rlabel_position(135)

    corr_ticks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
    ax.set_xticks(np.arccos(corr_ticks))
    ax.set_xticklabels([f"{c:g}" for c in corr_ticks], fontsize=8)
    ax.text(np.deg2rad(45), max_r * 1.16, "Coeficiente de correlación (R)",
             ha="center", va="center", fontsize=9, rotation=-45)
    ax.set_ylabel("Desviación estándar normalizada (σ simulado / σ observado)",
                   fontsize=8.5, labelpad=28)

    # --- Mapa de calor de fondo: RMSE centrado en función del punto ----
    # --- observado (pedido explícito de la usuaria) --------------------
    # El RMSE centrado de cualquier punto (r, theta) del diagrama respecto
    # del punto de referencia "Observado" (r=1, theta=0) tiene una fórmula
    # analítica cerrada (ley del coseno, la misma que ya usan los arcos
    # punteados de abajo): RMSE'^2 = 1 + r^2 - 2·r·cos(theta). Se evalúa
    # en toda la grilla (r, theta) del cuadrante y se pinta con
    # `contourf`, de modo que la TONALIDAD de cualquier punto del gráfico
    # -- no solo los marcadores de las corridas -- muestre de un vistazo
    # qué tan cerca está ese punto del ideal (observado = tonalidad
    # "buena"/verde, cada vez más lejos = "mala"/roja), usando la misma
    # paleta verde-ámbar-rojo del resto de la interfaz.
    theta_grid = np.linspace(0.0, np.pi / 2, 140)
    r_grid = np.linspace(0.0, max_r, 140)
    theta_mesh, r_mesh = np.meshgrid(theta_grid, r_grid)
    rmse_mesh = np.sqrt(np.clip(1.0 + r_mesh ** 2 - 2.0 * r_mesh * np.cos(theta_mesh), 0.0, None))
    heat_cmap = mcolors.LinearSegmentedColormap.from_list(
        "taylor_heat", [_GAUGE_GOOD, _GAUGE_WARN, _GAUGE_BAD])
    heat_vmax = max(float(np.nanmax(rmse_mesh)), 1e-6)
    heat = ax.contourf(theta_mesh, r_mesh, rmse_mesh, levels=18, cmap=heat_cmap,
                        vmin=0.0, vmax=heat_vmax, alpha=0.55, zorder=0, antialiased=True)
    # Barra de color HORIZONTAL, en una franja angosta debajo del propio
    # cuadrante (no a la derecha, donde ya vive la leyenda de corridas):
    # así nunca compite por espacio con la leyenda, sin importar cuántas
    # corridas se comparen ni cuán largos sean sus nombres.
    cax = fig.add_axes([0.145, 0.075, 0.545, 0.028])
    cbar = fig.colorbar(heat, cax=cax, orientation="horizontal")
    cbar.set_label("RMSE centrado (distancia al punto \"Observado\")", fontsize=7.3, labelpad=2)
    cbar.ax.tick_params(labelsize=7)

    # Arcos concéntricos de RMSE centrado (distancia al punto de
    # referencia (1,0) en coordenadas cartesianas), útiles para leer
    # el valor exacto de un vistazo, ahora sobre el fondo de calor.
    ref_r, ref_theta = 1.0, 0.0
    for rmse_c in np.arange(0.25, max_r + 0.5, 0.25):
        theta_c = np.linspace(0, np.pi / 2, 100)
        xc = ref_r + rmse_c * np.cos(theta_c)
        yc = rmse_c * np.sin(theta_c)
        rc = np.hypot(xc, yc)
        tc = np.arctan2(yc, xc)
        valid = (rc <= max_r) & (tc >= 0)
        if valid.any():
            ax.plot(tc[valid], rc[valid], color="#5B6472", lw=0.7, ls=":", zorder=1)

    # Punto de referencia (observado): r=1, correlación=1 (theta=0).
    ax.plot([0], [1], marker="*", markersize=16, color=OBS_COLOR, zorder=5,
             label="Observado (referencia)")

    for i, (name, r_norm, corr) in enumerate(points):
        st = _resolve_style(name, i, style_map)
        theta = np.arccos(np.clip(corr, -1, 1))
        ax.plot(theta, r_norm, marker=st["marker"], markersize=9, color=st["color"],
                 markeredgecolor="white", markeredgewidth=0.6,
                 linestyle="None", zorder=6, label=name)

    ax.set_title(title, pad=22)
    # La leyenda va en una franja fija AFUERA del cuadrante (a la
    # derecha de la figura, reservada arriba con `fig.add_axes`), no
    # adentro del gráfico: colocarla en la cuña vacía superior-
    # izquierda (como antes) funcionaba con una sola corrida, pero con
    # varias empezaba a taparse con las líneas/etiquetas de la grilla o
    # a recortarse contra el borde del lienzo. Con `bbox_to_anchor` y
    # sin `constrained_layout` (que antes recortaba la leyenda al ancho
    # del canvas), esto ya no pasa sin importar cuántas corridas se
    # comparen. La barra de color del mapa de calor va abajo (no a la
    # derecha), así que la leyenda conserva su posición de siempre.
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.05, 0.5), fontsize=8.5, framealpha=0.9)
    if leg is not None:
        leg.get_frame().set_linewidth(0.6)
    return fig


def pot_selection_plot(df: pd.DataFrame, date_col: str, obs_col: str,
                        pot_max: POTResult | None = None,
                        pot_min: POTResult | None = None) -> plt.Figure:
    """Hidrograma observado con los eventos POT (máximos y/o mínimos)
    resaltados, equivalente a "POT selection" en el menú de gráficos."""
    fig, ax = _new_fig()
    ax.plot(df[date_col], df[obs_col], color="#9A9A9A", lw=0.9, label=obs_col, zorder=1)
    if pot_max is not None:
        ax.scatter(pot_max.dates, pot_max.obs, color="#D55E00", marker="^", s=32, zorder=5,
                    edgecolors="white", linewidths=0.4,
                    label=f"Picos máximos (n={len(pot_max.obs)})")
    if pot_min is not None:
        ax.scatter(pot_min.dates, pot_min.obs, color="#0072B2", marker="v", s=32, zorder=5,
                    edgecolors="white", linewidths=0.4,
                    label=f"Picos mínimos (n={len(pot_min.obs)})")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Caudal [m³/s]")
    ax.set_title("Selección de eventos extremos independientes (POT)")
    _style_legend(ax)
    fig.autofmt_xdate(rotation=20, ha="right")
    return fig


def extreme_value_plot(pot_result: POTResult, box_cox_values: dict | None = None,
                        ylabel: str = "Caudal [m³/s]",
                        style_map: dict | None = None) -> plt.Figure:
    """Gráfico de valor extremo vs. periodo de retorno (escala log en
    X), observado y cada corrida simulada superpuestos, en escala
    original o Box-Cox (columnas 11/12/13/14 del menú de gráficos)."""
    fig, ax = _new_fig()
    T = pot_result.return_period
    obs_vals = pot_result.obs if box_cox_values is None else box_cox_values["obs_bc"]
    ax.scatter(T, obs_vals, color=OBS_COLOR, marker="o", s=26, label="Observado", zorder=5,
                edgecolors="white", linewidths=0.4)
    sim_source = pot_result.sim if box_cox_values is None else \
        {k: v["sim_bc"] for k, v in box_cox_values["por_corrida"].items()}
    for i, (name, vals) in enumerate(sim_source.items()):
        st = _resolve_style(name, i, style_map)
        ax.scatter(T, vals, color=st["color"], marker=st["marker"], s=22, alpha=0.75,
                    label=name, linewidths=0)
    ax.set_xscale("log")
    ax.set_xlabel("Periodo de retorno T [años]")
    ax.set_ylabel(ylabel if box_cox_values is None else f"{ylabel} (transformado Box-Cox)")
    label_kind = "máximos" if pot_result.kind == "max" else "mínimos"
    ax.set_title(f"Valores extremos {label_kind} vs. periodo de retorno")
    _style_legend(ax)
    ax.grid(which="minor", alpha=0.15, linestyle=":")
    return fig


def placeholder_message_plot(message: str, title: str = "") -> plt.Figure:
    """Figura simple con un mensaje centrado (sin ejes), para cuando un
    gráfico no se puede generar con los datos/parámetros actuales — por
    ejemplo, Box-Cox cuando los eventos extremos seleccionados no tienen
    variación. Se usa en vez de dejar la pestaña vacía o hacer fallar
    todo el análisis por un solo gráfico."""
    fig, ax = _new_fig()
    ax.axis("off")
    if title:
        ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True,
             fontsize=10.5, color="#555555", transform=ax.transAxes)
    return fig


# ---------------------------------------------------------------------------
# Medidor / escala de interpretación de un indicador (pestaña "Validación",
# panel didáctico por método): barra horizontal con bandas de color
# Malo/Regular/Bueno y un marcador por corrida, o -para indicadores sin
# rango universal fijo (MAE/STD/RMSE)- una comparación de barras entre las
# corridas analizadas. Los colores replican los de `gui_qt.theme` (no se
# importa ese módulo para no acoplar este paquete, usable también sin
# interfaz gráfica, a la GUI).
# ---------------------------------------------------------------------------
_GAUGE_GOOD = "#1E9E6B"
_GAUGE_WARN = "#D8A02A"
_GAUGE_BAD = "#DD5353"
_GAUGE_NEUTRAL = "#64748B"


def _blend_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def _band_color_for(v: float, bands: list[tuple[float, float, str]]) -> str:
    for lo, hi, color in bands:
        if lo <= v <= hi:
            return color
    return _GAUGE_NEUTRAL


def indicator_gauge_plot(indicator: str, values_by_run: dict, scale: dict,
                          obs_mean: float | None = None) -> plt.Figure:
    """Gráfico de "escala de interpretación" de un indicador de bondad de
    ajuste: para indicadores con rango de referencia conocido (EF, R, CD,
    KGE, Model Skill, CR4, CR5, PBIAS, CR1) dibuja una barra con bandas
    Malo/Regular/Bueno y un marcador por corrida simulada; para MAE/STD/
    RMSE, que no tienen un rango universal (dependen de las unidades y
    magnitud del caudal), dibuja en cambio una comparación de barras entre
    las corridas analizadas (menor = mejor), con una línea de referencia
    al 10% del caudal medio observado si se provee `obs_mean`."""
    gauge_type = scale.get("gauge_type", "open_error")
    names = list(values_by_run.keys())

    if gauge_type == "open_error":
        n = max(1, len(names))
        fig = plt.Figure(figsize=(7.6, 0.85 + 0.46 * n), dpi=140, constrained_layout=True)
        ax = fig.add_subplot(111)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        vals = [float(values_by_run[k]) for k in names]
        order = np.argsort(vals)  # ascendente: menor error (mejor) primero
        names_sorted = [names[i] for i in order]
        vals_sorted = [vals[i] for i in order]
        neutral = bool(scale.get("neutral"))
        if neutral:  # sin rangos: orden original y color neutro
            names_sorted, vals_sorted = names, vals
            colors_bar = [_GAUGE_NEUTRAL] * n
        else:
            colors_bar = [_blend_hex(_GAUGE_GOOD, _GAUGE_BAD, i / max(1, n - 1))
                          for i in range(n)]
        y_pos = np.arange(n)
        ax.barh(y_pos, vals_sorted, color=colors_bar, edgecolor="white", height=0.55, zorder=3)
        xmax = max(vals_sorted) if vals_sorted else 1.0
        for y, v in zip(y_pos, vals_sorted):
            ax.text(v + xmax * 0.015, y, f"{v:.4g}", va="center", ha="left",
                     fontsize=9, color="#333333")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names_sorted)
        ax.invert_yaxis()
        ax.set_ylim(n - 0.35, -0.85)
        if obs_mean and obs_mean > 0 and not scale.get("neutral"):
            ref = 0.10 * abs(obs_mean)
            ax.axvline(ref, color=_GAUGE_NEUTRAL, ls="--", lw=1.0, zorder=2)
            ax.text(ref, -0.85, "10% del caudal medio observado (ref.)",
                     fontsize=7.5, color=_GAUGE_NEUTRAL, va="bottom", ha="left")
        ax.set_xlabel(f"{indicator} — menor es mejor\n(sin rango universal fijo: se compara entre corridas)",
                       fontsize=9.5)
        ax.grid(axis="x", alpha=0.3)
        return fig

    fig = plt.Figure(figsize=(7.6, 2.3), dpi=140, constrained_layout=True)
    ax = fig.add_subplot(111)

    axis_hi = scale["axis_hi"]
    if gauge_type == "symmetric_bias":
        axis_lo = -axis_hi
        t_bueno, t_regular = scale["t_bueno"], scale["t_regular"]
        bands = [
            (axis_lo, -t_regular, _GAUGE_BAD),
            (-t_regular, -t_bueno, _GAUGE_WARN),
            (-t_bueno, t_bueno, _GAUGE_GOOD),
            (t_bueno, t_regular, _GAUGE_WARN),
            (t_regular, axis_hi, _GAUGE_BAD),
        ]
        mult = 100.0 if scale.get("as_pct") else 1.0
        display_vals = {k: float(v) * mult for k, v in values_by_run.items()}
        xlabel = f"{indicator} — 0 es el ajuste ideal (sin sesgo); bandas en ±{t_bueno:g}/±{t_regular:g}"
    else:  # "higher_better"
        axis_lo = scale.get("axis_lo", 0.0)
        t_regular, t_bueno = scale["t_regular"], scale["t_bueno"]
        bands = [
            (axis_lo, t_regular, _GAUGE_BAD),
            (t_regular, t_bueno, _GAUGE_WARN),
            (t_bueno, axis_hi, _GAUGE_GOOD),
        ]
        display_vals = {k: float(v) for k, v in values_by_run.items()}
        xlabel = f"{indicator} — más a la derecha (verde) es mejor"

    for lo, hi, color in bands:
        lo_c, hi_c = max(lo, axis_lo), min(hi, axis_hi)
        if hi_c > lo_c:
            ax.axvspan(lo_c, hi_c, color=color, alpha=0.30, lw=0, zorder=1)

    ax.set_xlim(axis_lo, axis_hi)
    ax.set_ylim(-1.15, 1.55)
    ax.set_yticks([])
    ax.axhline(0.0, color="#B0B0B0", lw=1.1, zorder=2)

    for i, (name, val) in enumerate(display_vals.items()):
        v_clamped = min(max(val, axis_lo), axis_hi)
        color = _band_color_for(v_clamped, bands)
        sign = 1 if i % 2 == 0 else -1
        level = i // 2
        y_label = sign * (0.45 + 0.38 * level)
        ax.plot([v_clamped], [0.0], marker="v" if sign > 0 else "^", markersize=12,
                 color=color, markeredgecolor="#1B2430", markeredgewidth=0.6, zorder=5)
        ax.annotate(f"{name}\n{val:.3g}" + (" *" if val != v_clamped else ""),
                     xy=(v_clamped, 0.0), xytext=(v_clamped, y_label),
                     ha="center", va="center", fontsize=8, color="#1B2430",
                     arrowprops=dict(arrowstyle="-", color="#9AA5B5", lw=0.7), zorder=6)

    ax.set_xlabel(xlabel)
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(left=False)
    ax.grid(False)
    return fig


def _grouped_bars(ax, df: pd.DataFrame, ylabel: str = "", title: str = "",
                   style_map: dict | None = None):
    """Barras agrupadas: una barra por modelo (columna de `df`),
    agrupadas por variable (índice de `df`). Reutilizado por los
    gráficos de comparación EF/KGE y PBIAS entre varias variables
    (p. ej. caudal + varios piezómetros) y varios modelos, del módulo
    de análisis múltiple/en paralelo."""
    variables = [str(v) for v in df.index]
    models = [str(c) for c in df.columns]
    n_models = max(1, len(models))
    x = np.arange(len(variables))
    width = min(0.82 / n_models, 0.26)
    offsets = (np.arange(n_models) - (n_models - 1) / 2) * width
    for i, model in enumerate(models):
        vals = df[df.columns[i]].to_numpy(dtype=float)
        color = _resolve_style(model, i, style_map)["color"]
        ax.bar(x + offsets[i], vals, width=width, label=model,
               color=color, edgecolor="white", linewidth=0.6, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(variables)
    ax.axhline(0.0, color="#3A3A3A", lw=1.0, zorder=2)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    return ax


def ef_kge_comparison_plot(ef_df: pd.DataFrame, kge_df: pd.DataFrame,
                            title: str = "Comparación de indicadores de ajuste (EF y KGE) "
                                          "por variable y modelo",
                            style_map: dict | None = None) -> plt.Figure:
    """Dos gráficos de barras agrupadas lado a lado -- Eficiencia de
    Nash-Sutcliffe (EF) y KGE -- comparando varios modelos a través de
    varias variables analizadas en paralelo (p. ej. caudal y varios
    piezómetros). Responde a poder comparar, de un vistazo, qué modelo
    se ajusta mejor en cada variable y en conjunto, no solo dentro de
    una variable a la vez."""
    fig = plt.Figure(figsize=(11.0, 4.6), dpi=140, constrained_layout=True)
    ax1 = fig.add_subplot(121)
    ax2 = fig.add_subplot(122)
    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    _grouped_bars(ax1, ef_df, ylabel="Valor del indicador", title="Eficiencia de Nash-Sutcliffe (EF)",
                  style_map=style_map)
    _grouped_bars(ax2, kge_df, ylabel="", title="Índice KGE", style_map=style_map)
    _style_legend(ax1)
    fig.suptitle(title, fontsize=11.5, fontweight="bold")
    return fig


def pbias_comparison_plot(pbias_df: pd.DataFrame, band: float = 10.0,
                           title: str = "Sesgo porcentual (PBIAS) por variable y modelo",
                           style_map: dict | None = None) -> plt.Figure:
    """Barras agrupadas del sesgo porcentual (PBIAS, %) de varios
    modelos a través de varias variables, con una banda sombreada de
    sesgo aceptable (±`band`%, 10% por defecto) para ubicar de un
    vistazo qué combinaciones variable/modelo están dentro de un rango
    razonable. Negativo = el modelo subestima lo observado; positivo =
    lo sobreestima."""
    fig, ax = _new_fig(figsize=(8.6, 4.4))
    ax.axhspan(-band, band, color="#2E7D32", alpha=0.12, zorder=1,
               label=f"Sesgo aceptable (±{band:g}%)")
    _grouped_bars(ax, pbias_df, ylabel="PBIAS [%]", style_map=style_map)
    ax.set_title(f"{title}\n(negativo = el modelo subestima lo observado)")
    _style_legend(ax)
    return fig


def average_ranking_plot(ranking_df: pd.DataFrame,
                          score_col: str = "Puntaje promedio (0-1)") -> plt.Figure:
    """Barra horizontal del puntaje promedio de cada modelo (calculado
    sobre todas las variables analizadas en el módulo de análisis
    múltiple), ordenado de mejor a peor -- el gráfico que acompaña al
    ranking promedio por modelo pedido para ver, de un vistazo, los
    resultados de toda la parte de validación."""
    names = [str(n) for n in ranking_df.index]
    vals = ranking_df[score_col].astype(float).to_numpy()
    n = max(1, len(names))
    fig = plt.Figure(figsize=(7.6, 0.9 + 0.5 * n), dpi=140, constrained_layout=True)
    ax = fig.add_subplot(111)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    order = np.argsort(vals)[::-1]  # descendente: mejor puntaje primero
    names_sorted = [names[i] for i in order]
    vals_sorted = [vals[i] for i in order]
    colors_bar = [_blend_hex(_GAUGE_BAD, _GAUGE_GOOD, max(0.0, min(1.0, v))) for v in vals_sorted]
    y_pos = np.arange(n)
    ax.barh(y_pos, vals_sorted, color=colors_bar, edgecolor="white", height=0.55, zorder=3)
    for y, v in zip(y_pos, vals_sorted):
        ax.text(v + 0.015, y, f"{v:.3f}", va="center", ha="left", fontsize=9, color="#333333")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names_sorted)
    ax.invert_yaxis()
    ax.set_xlim(0, max(1.08, (max(vals_sorted) if vals_sorted else 1.0) * 1.1))
    ax.set_xlabel("Puntaje promedio compuesto (0-1) — promedio sobre todas las variables analizadas")
    ax.grid(axis="x", alpha=0.3)
    return fig


# ---------------------------------------------------------------------------
# Grillas del análisis múltiple/en paralelo: una figura combinada por cada
# variable analizada (caudal, piezómetros, etc.), con todos los modelos
# superpuestos en el mismo color en todas las variables -- equivalentes a
# las Figuras 1 y 2 de un informe de validación con varias variables
# instrumentadas (p. ej. caudal de filtración + piezómetros de una presa).
# A diferencia de los gráficos "Dispersión"/"Comparación" de la pestaña
# Validación (una sola variable, varias corridas), acá se arma UNA figura
# con un panel POR VARIABLE, para poder comparar todo el análisis múltiple
# de un vistazo en vez de pestaña por pestaña.
# ---------------------------------------------------------------------------

def _multi_var_model_order(data_by_var: dict, model_index: int) -> list[str]:
    """Orden de modelos consistente (mismo color para el mismo modelo en
    todos los paneles/variables): el orden en que aparecen por primera
    vez recorriendo las variables, no el orden -alfabético o de
    diccionario- de cada variable por separado (que podría variar si a
    alguna variable le falta un modelo)."""
    seen: list[str] = []
    for entry in data_by_var.values():
        sim_dict = entry[model_index]
        for m in sim_dict:
            if m not in seen:
                seen.append(m)
    return seen


def multi_variable_dispersion_grid_plot(
        data_by_var: dict[str, tuple], model_order: list[str] | None = None,
        title: str = "Dispersión observado vs. calculado (bisectriz 1:1) por variable y modelo",
        style_map: dict | None = None,
) -> plt.Figure:
    """Grilla de gráficos de dispersión (bisectriz 1:1), un panel por
    variable analizada en el módulo de análisis múltiple/en paralelo
    (p. ej. caudal y varios piezómetros), con todos los modelos
    superpuestos y el MISMO color para un modelo dado en todos los
    paneles -- para poder comparar de un vistazo qué modelo se ajusta
    mejor, y en qué variables, sin ir pestaña por pestaña.

    `data_by_var` es {nombre_variable: (observado, {modelo: simulado})}.
    La cantidad de columnas de la grilla se ajusta sola según cuántas
    variables se analicen, y los paneles sobrantes (si el número de
    variables no llena la última fila) quedan ocultos en vez de vacíos."""
    names = list(data_by_var.keys())
    n = len(names)
    if n == 0:
        raise ValueError("No hay variables para graficar (defina al menos una en la tabla).")
    if model_order is None:
        model_order = _multi_var_model_order(data_by_var, 1)

    ncols = 1 if n == 1 else (2 if n <= 6 else 3)
    nrows = int(np.ceil(n / ncols))
    fig = plt.Figure(figsize=(5.6 * ncols + 1.6, 5.0 * nrows + 0.5), dpi=130,
                      constrained_layout=True)
    axes = fig.subplots(nrows, ncols, squeeze=False)

    for idx, name in enumerate(names):
        r, c = divmod(idx, ncols)
        ax = axes[r][c]
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        obs, sim_dict = data_by_var[name]
        obs_arr = np.asarray(obs, dtype=float)
        all_vals = [obs_arr]
        for m in model_order:
            if m not in sim_dict:
                continue
            sim_arr = np.asarray(sim_dict[m], dtype=float)
            mask = ~np.isnan(obs_arr) & ~np.isnan(sim_arr)
            if mask.sum() < 1:
                continue
            all_vals.append(sim_arr[mask])
            color = _resolve_style(m, model_order.index(m), style_map)["color"]
            ax.scatter(obs_arr[mask], sim_arr[mask], s=18, alpha=0.65, color=color,
                        linewidths=0, label=m, zorder=3)
        finite_vals = [v[np.isfinite(v)] for v in all_vals if np.isfinite(v).any()]
        if finite_vals:
            lo = min(v.min() for v in finite_vals)
            hi = max(v.max() for v in finite_vals)
            if hi > lo:
                ax.plot([lo, hi], [lo, hi], color=OBS_COLOR, lw=1.0, ls="--", label="1:1", zorder=1)
        ax.set_title(str(name), fontsize=10.5, fontweight="bold")
        ax.set_xlabel(f"Observado — {name}", fontsize=9)
        ax.set_ylabel(f"Calculado — {name}", fontsize=9)
        ax.tick_params(labelsize=8)
        leg = ax.legend(loc="best", fontsize=7.5, framealpha=0.9)
        if leg is not None:
            leg.get_frame().set_linewidth(0.5)

    for idx in range(n, nrows * ncols):
        r, c = divmod(idx, ncols)
        axes[r][c].axis("off")

    fig.suptitle(title, fontsize=12.5, fontweight="bold")
    return fig


def multi_variable_timeseries_grid_plot(
        data_by_var: dict[str, tuple], x_label: str = "Número de fila",
        model_order: list[str] | None = None,
        title: str = "Series observadas vs. calculadas por variable y modelo",
        style_map: dict | None = None,
) -> plt.Figure:
    """Paneles apilados (uno por variable, eje X compartido), cada uno
    con la serie observada y cada modelo simulado superpuestos -- para
    ver de un vistazo la forma de toda la instrumentación (p. ej.
    caudal de filtración y varios piezómetros de una presa) frente a
    los modelos comparados, en una sola figura en vez de una pestaña
    por variable.

    `data_by_var` es {nombre_variable: (x, observado, {modelo: simulado})}.
    Solo el panel superior lleva leyenda (misma leyenda para todos, ya
    que el color de cada modelo es consistente en todos los paneles) y
    solo el panel inferior lleva la etiqueta del eje X, para no repetir
    lo mismo en cada panel."""
    names = list(data_by_var.keys())
    n = len(names)
    if n == 0:
        raise ValueError("No hay variables para graficar (defina al menos una en la tabla).")
    if model_order is None:
        model_order = _multi_var_model_order(data_by_var, 2)

    fig = plt.Figure(figsize=(10.2, 2.35 * n + 0.7), dpi=130, constrained_layout=True)
    axes_arr = fig.subplots(n, 1, sharex=True, squeeze=False)
    axes = [axes_arr[i][0] for i in range(n)]

    is_datetime = False
    try:
        first_x = np.asarray(data_by_var[names[0]][0])
        is_datetime = np.issubdtype(first_x.dtype, np.datetime64)
    except Exception:
        is_datetime = False

    for i, name in enumerate(names):
        ax = axes[i]
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        x, obs, sim_dict = data_by_var[name]
        marker_obs = "o" if len(obs) <= 60 else None
        ax.plot(x, obs, color=OBS_COLOR, lw=1.3, marker=marker_obs, markersize=3,
                 label="Observado", zorder=3)
        for m in model_order:
            if m not in sim_dict:
                continue
            # Aspecto por defecto igual al original (línea punteada, color
            # por índice): un `style_map` con color y/o línea propios para
            # `m` los reemplaza; sin personalizar, no cambia nada.
            custom = (style_map or {}).get(m) or {}
            color = custom.get("color") or COLORS[model_order.index(m) % len(COLORS)]
            ls = custom.get("linestyle") or "--"
            ax.plot(x, sim_dict[m], color=color, ls=ls, lw=1.1, alpha=0.9, label=m, zorder=2)
        ax.set_ylabel(str(name), fontsize=9.5, fontweight="bold")
        ax.tick_params(labelsize=8)
        if i == 0:
            leg = ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.32),
                             ncol=min(5, 1 + len(model_order)), fontsize=8, framealpha=0.9)
            if leg is not None:
                leg.get_frame().set_linewidth(0.6)

    axes[-1].set_xlabel(x_label)
    if is_datetime:
        fig.autofmt_xdate(rotation=20, ha="right")
    fig.suptitle(title, fontsize=12.5, fontweight="bold")
    return fig


# ---------------------------------------------------------------------------
# Tabla representativa como figura (imagen): para que las tablas de los
# métodos estadísticos (resumen de métodos usados, resultados por
# indicador...) se vean estéticas, se puedan exportar a PNG igual que
# cualquier gráfico, y -- agregadas a `self.last_figures` en la GUI --
# fluyan automáticamente al reporte exportado (PDF/Word/Excel) como una
# figura más, con su propia descripción (ver `FIGURE_DESCRIPTIONS`), sin
# plomería adicional en `report.py`.
# ---------------------------------------------------------------------------
import textwrap

# Mismos archivos .ttf que `ct_tool.report._FONT_FILES` usa para incrustar
# la tipografía elegida por la usuaria en el PDF/Word/Excel (reportlab).
# Esta tabla se genera como una FIGURA de matplotlib (no como texto de
# reportlab/python-docx), así que sin esto quedaba siempre con la fuente
# por defecto de matplotlib (DejaVu Sans) en vez de la elegida en el
# diálogo "Estilo de reporte" -- se registra el mismo .ttf en el gestor de
# fuentes de matplotlib para que la tabla salga con la MISMA tipografía
# que el resto del reporte. Se duplica aquí en vez de importarse desde
# `report.py` por la misma razón que `report.py` duplica `_base_dir()`:
# este módulo no debe depender de `report.py`.
_REPORT_FONT_FILES = {
    "Arial": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "Times New Roman": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "Calibri": "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
    "Cambria": "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
}
_mpl_font_cache: dict[str, str | None] = {}


def _mpl_font_family(report_font_family: str | None) -> str | None:
    """Nombre de familia tipográfica que matplotlib puede usar (vía
    `fontfamily=...`) para la opción de fuente elegida en el reporte
    ("Arial"/"Times New Roman"/"Calibri"/"Cambria"). Registra el .ttf
    correspondiente en el gestor de fuentes de matplotlib la primera vez
    que se pide. Devuelve `None` si no hay opción, el archivo no existe
    en este sistema, o falla el registro -- en cuyo caso la figura cae
    en silencio a la fuente por defecto de matplotlib, sin romperse."""
    if not report_font_family:
        return None
    if report_font_family in _mpl_font_cache:
        return _mpl_font_cache[report_font_family]
    path = _REPORT_FONT_FILES.get(report_font_family)
    family = None
    if path and Path(path).exists():
        try:
            from matplotlib import font_manager
            font_manager.fontManager.addfont(path)
            family = font_manager.FontProperties(fname=path).get_name()
        except Exception:
            family = None
    _mpl_font_cache[report_font_family] = family
    return family


def styled_table_figure(df: pd.DataFrame, title: str = "",
                         col_wrap_widths: dict[str, int] | None = None,
                         font_family: str | None = None) -> plt.Figure:
    """Convierte un DataFrame en una figura de tabla con aspecto
    académico/formal: encabezado en negrita, y solo TRES filetes
    horizontales (uno grueso arriba del encabezado, uno bajo el
    encabezado y uno grueso al pie de la tabla) -- sin grilla ni líneas
    verticales, igual que una tabla de artículo científico (estilo
    "booktabs", como en las tablas de materiales de presas CFRD de la
    bibliografía que sirvieron de referencia). El texto largo de cada
    celda se ajusta a varias líneas para que la tabla no quede
    desbordada.

    `col_wrap_widths`: ancho de ajuste de texto (en caracteres) por
    columna (por nombre); por defecto, 28 caracteres para todas.
    `font_family`: una de `ct_tool.report.REPORT_FONT_CHOICES`
    ("Arial"/"Times New Roman"/"Calibri"/"Cambria"); si se pasa, la
    tabla sale con la misma tipografía elegida para el resto del
    reporte (ver `_mpl_font_family`)."""
    mpl_family = _mpl_font_family(font_family)
    cols = [str(c) for c in df.columns]
    wrap_w = {c: 28 for c in cols}
    if col_wrap_widths:
        wrap_w.update(col_wrap_widths)

    def _wrap(value, width):
        text = "" if value is None else str(value)
        if not text:
            return ""
        return "\n".join(textwrap.wrap(text, width=width)) or text

    wrapped_rows = [
        [_wrap(row[c], wrap_w.get(c, 28)) for c in cols]
        for _, row in df.iterrows()
    ]
    header_cells = [_wrap(c, wrap_w.get(c, 28)) for c in cols]

    n_rows = len(wrapped_rows)
    n_cols = len(cols)
    row_lines = [max(1, max((cell.count("\n") + 1 for cell in row), default=1))
                 for row in wrapped_rows] or [1]
    header_lines = max(1, max((h.count("\n") + 1 for h in header_cells), default=1))

    # Alto de cada fila como FRACCIÓN del alto total de la tabla
    # (header_lines + Σ row_lines), de modo que la suma de alturas sea
    # siempre exactamente 1.0 -- si no, con alturas "a ojo" la tabla
    # termina más alta o más baja que el eje que la contiene y se
    # recorta o se superpone con el título (mismo tipo de bug que el
    # ancho de columnas de la tabla resumen del PDF, resuelto ahí con
    # pesos proporcionales).
    total_lines = header_lines + sum(row_lines)
    header_h = header_lines / total_lines
    row_h_frac = [lines / total_lines for lines in row_lines]

    col_weights = [wrap_w.get(c, 28) for c in cols]
    total_w = sum(col_weights) or 1.0
    fig_w = max(6.0, min(16.0, 1.2 + total_w * 0.095))
    fig_h = max(2.2, 0.5 + total_lines * 0.3)
    title_frac = 0.55 / fig_h if title else 0.0  # franja fija (~0.4") para el título

    fig = plt.Figure(figsize=(fig_w, fig_h), dpi=150)
    ax = fig.add_axes([0.015, 0.02, 0.97, 0.96 - title_frac])
    ax.axis("off")
    if title:
        title_kwargs = dict(fontsize=12, fontweight="bold", y=0.98)
        if mpl_family:
            title_kwargs["fontfamily"] = mpl_family
        fig.suptitle(title, **title_kwargs)

    tbl = ax.table(cellText=wrapped_rows if wrapped_rows else [[""] * n_cols],
                    colLabels=header_cells, cellLoc="left", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)

    for j, w in enumerate(col_weights):
        for r in range(n_rows + 1):
            tbl[r, j].set_width(w / total_w)

    # Solo TRES filetes horizontales (arriba del encabezado, bajo el
    # encabezado y al pie de la tabla), sin grilla ni líneas verticales
    # ni líneas entre filas de datos -- estilo "booktabs" de una tabla de
    # artículo científico. `visible_edges` controla qué lados del
    # rectángulo de cada celda se dibujan ("BT" = arriba+abajo, "B" =
    # solo abajo, "" = ninguno).
    for j in range(n_cols):
        cell = tbl[0, j]
        cell.set_text_props(fontweight="bold", color="black", ha="center")
        if mpl_family:
            cell.get_text().set_fontfamily(mpl_family)
        cell.set_facecolor("white")
        cell.set_edgecolor("black")
        cell.set_linewidth(1.2)
        cell.visible_edges = "BT"
        cell.set_height(header_h)
        cell.PAD = 0.035

    for r in range(1, n_rows + 1):
        is_last = r == n_rows
        for j in range(n_cols):
            cell = tbl[r, j]
            cell.set_facecolor("white")
            if mpl_family:
                cell.get_text().set_fontfamily(mpl_family)
            if is_last:
                cell.set_edgecolor("black")
                cell.set_linewidth(1.1)
                cell.visible_edges = "B"
            else:
                cell.visible_edges = ""
            cell.set_height(row_h_frac[r - 1])
            cell.PAD = 0.035

    return fig


ALL_PLOTS_DESCRIPTIONS = {
    1: "Caudal en el tiempo - escala lineal",
    2: "Caudal en el tiempo - escala logarítmica",
    3: "Caudal acumulado",
    4: "Residuos (Simulado - Observado) en el tiempo",
    5: "Caudal ordenado (curva de duración)",
    6: "Residuos vs. observado",
    7: "Dispersión (bisectriz) - todos los datos",
    8: "Dispersión (bisectriz) - máximos POT",
    9: "Dispersión (bisectriz) - mínimos POT",
    10: "Selección de eventos POT",
    11: "Valores extremos máximos vs. periodo de retorno",
    12: "Valores extremos mínimos vs. periodo de retorno",
    13: "Box-Cox - máximos",
    14: "Box-Cox - 1/mínimos",
}


# ---------------------------------------------------------------------------
# Descripción didáctica de cada gráfico de diagnóstico: qué muestra y cómo
# leerlo, para que ninguna figura quede "muda" — ni en la interfaz (pestañas
# de gráficos) ni en los reportes exportados (PDF/Word/Excel), donde antes
# solo aparecía la imagen sin ningún texto que la explique. Vive acá (no en
# la GUI) para que tanto `gui_qt.main_window` como `report.py` (que no
# depende de PyQt) usen el mismo texto sin duplicarlo.
# ---------------------------------------------------------------------------
FIGURE_DESCRIPTIONS = {
    "Hidrograma": "Caudal observado y simulado(s) en el tiempo, en escala "
        "lineal. Es el primer gráfico a revisar: permite ver a simple "
        "vista si el modelo sigue la forma general del hidrograma "
        "(crecidas, recesiones, estiajes) y si hay desfases en el tiempo.",
    "Hidrograma (log)": "El mismo hidrograma, pero con el eje de caudal en "
        "escala logarítmica. Comprime los picos de crecida y \"estira\" "
        "los caudales bajos, así que es el gráfico indicado para revisar "
        "qué tan bien se simulan los estiajes — algo que en escala lineal "
        "suele quedar aplastado en la parte baja del gráfico.",
    "Caudal acumulado": "Curva de masa: la suma acumulada del caudal a lo "
        "largo del tiempo. Su pendiente refleja el caudal medio en cada "
        "tramo, así que si la curva simulada se separa de la observada de "
        "forma sostenida (no solo en un evento puntual), indica un sesgo "
        "de volumen (ver también CR1/PBIAS en la pestaña Validación).",
    "Residuos (tiempo)": "El error del modelo (simulado − observado) en "
        "cada instante, a lo largo del tiempo. Residuos que oscilan "
        "alrededor de cero sin patrón indican un buen ajuste; residuos "
        "que se agrupan por temporada o que crecen con el tiempo sugieren "
        "un problema sistemático de calibración.",
    "Residuos vs. Obs": "El mismo error, pero graficado contra el caudal "
        "observado en vez del tiempo. Sirve para detectar si el modelo "
        "falla más en los caudales altos, en los bajos, o de forma "
        "pareja en todo el rango — un patrón en forma de embudo o "
        "tendencia indica que el error depende de la magnitud del caudal.",
    "Curva de duración": "Caudal ordenado de mayor a menor contra su "
        "probabilidad de excedencia (curva de permanencia). Es el gráfico "
        "estándar en hidrología para comparar el régimen general de "
        "caudales (no evento por evento): si las curvas observada y "
        "simulada se superponen bien en todo el rango, el modelo "
        "reproduce correctamente tanto los caudales altos como los bajos.",
    "Bisectriz - todos": "Dispersión de todos los pares observado-simulado, "
        "con la línea 1:1 (bisectriz) como referencia de ajuste perfecto. "
        "Puntos por encima de la bisectriz indican sobreestimación en ese "
        "rango de caudal; por debajo, subestimación. Qué tan pegados están "
        "los puntos a la línea se relaciona directamente con R y EF.",
    "Bisectriz - máximos": "El mismo gráfico de dispersión 1:1, mostrando "
        "únicamente los eventos extremos máximos (picos de crecida) "
        "seleccionados por el análisis POT — útil para juzgar el ajuste "
        "del modelo específicamente en las crecidas, sin que lo \"diluyan\" "
        "los muchos datos de caudal medio/bajo.",
    "Bisectriz - mínimos": "El mismo gráfico de dispersión 1:1, mostrando "
        "únicamente los eventos extremos mínimos (estiajes) seleccionados "
        "por el análisis POT — útil para juzgar el ajuste del modelo "
        "específicamente en época seca.",
    "Selección POT": "El hidrograma observado con los picos de crecida "
        "(triángulos hacia arriba) y los mínimos de estiaje (triángulos "
        "hacia abajo) que el programa identificó automáticamente como "
        "eventos extremos independientes. Revisar este gráfico ayuda a "
        "confirmar que los parámetros de separación mínima y umbral (ver "
        "pestaña Extremos) están seleccionando eventos razonables.",
    "Extremos máximos": "Los valores de los picos de crecida (observado y "
        "cada corrida simulada) graficados contra su periodo de retorno "
        "empírico T, en escala logarítmica. Es el gráfico típico de "
        "análisis de frecuencia de crecidas: si los puntos simulados "
        "siguen de cerca a los observados en todo el rango de T, el "
        "modelo reproduce bien tanto las crecidas frecuentes como las "
        "más raras (mayor periodo de retorno).",
    "Extremos mínimos": "Lo mismo que el gráfico anterior, pero para los "
        "eventos de estiaje: caudal mínimo de cada evento vs. su periodo "
        "de retorno, observado y simulado.",
    "Box-Cox máximos": "Los mismos valores extremos máximos, transformados "
        "con Box-Cox (ver teoría en la pestaña Extremos) para estabilizar "
        "su varianza antes de comparar. La transformación no cambia el "
        "orden de los datos, pero hace que las diferencias entre "
        "observado y simulado se puedan interpretar en una escala más "
        "cercana a la normal, con errores estadísticamente más comparables.",
    "Box-Cox 1/mínimos": "Los eventos de estiaje, transformados con Box-Cox "
        "aplicado al recíproco (1/caudal) — la convención estándar para "
        "estabilizar la varianza de caudales mínimos, que de otra forma "
        "quedarían muy comprimidos cerca de cero.",
    "Dispersión (Observado vs. Simulado)": "Todos los pares observado-simulado "
        "de la Validación, con la línea 1:1 (bisectriz) como referencia de "
        "ajuste perfecto. Funciona con cualquier tipo de dato (no solo "
        "caudal): puntos por encima de la bisectriz indican sobreestimación "
        "del modelo; por debajo, subestimación. Qué tan pegados están los "
        "puntos a la línea se relaciona directamente con R y EF.",
    "Comparación (Observado vs. Simulado)": "Observado y simulado(s) "
        "graficados uno junto al otro contra el «Eje X» elegido (fecha, "
        "profundidad, distancia, número de ensayo...) o, si no se eligió "
        "ninguno, contra el número de fila. Es el gráfico general de esta "
        "herramienta cuando se usa para validar datos que no son series de "
        "tiempo hidrológicas — por ejemplo, profundidad vs. asentamiento en "
        "geotecnia.",
    "Diagrama de Taylor": "Resume en un solo gráfico tres indicadores a la "
        "vez para cada corrida simulada: la correlación con el observado "
        "(ángulo respecto al eje horizontal), la desviación estándar "
        "normalizada (distancia al centro) y el error cuadrático medio "
        "centrado (distancia al punto \"Observado\", marcado con una "
        "estrella — los arcos punteados son líneas de igual RMSE "
        "centrado). El fondo del gráfico es un mapa de calor: la "
        "tonalidad de CUALQUIER punto del cuadrante (no solo los "
        "marcadores) muestra qué tan lejos está ese punto del ideal "
        "(verde = cerca del observado, rojo = lejos), con su propia "
        "barra de color debajo. Cuanto más cerca esté una corrida de la "
        "estrella (y más verde sea la zona donde cae), mejor reproduce "
        "en conjunto la forma y variabilidad del observado.",
    "Comparación EF y KGE por variable y modelo": "Del módulo de análisis "
        "múltiple/en paralelo: eficiencia de Nash-Sutcliffe (EF) y KGE de "
        "cada modelo, agrupadas por variable analizada (p. ej. caudal y "
        "varios piezómetros). Permite ver de un vistazo qué modelo se "
        "ajusta mejor en cada variable, y si ese desempeño es consistente "
        "entre variables o cambia de una a otra.",
    "Comparación PBIAS por variable y modelo": "Del módulo de análisis "
        "múltiple/en paralelo: sesgo porcentual (PBIAS) de cada modelo, "
        "agrupado por variable analizada, con una banda sombreada de sesgo "
        "aceptable (±10% por defecto). Negativo significa que el modelo "
        "subestima lo observado; positivo, que lo sobreestima.",
    "Ranking promedio por modelo": "Del módulo de análisis múltiple/en "
        "paralelo: puntaje compuesto de cada modelo promediado sobre todas "
        "las variables analizadas (no una variable a la vez), para "
        "resumir en un solo número qué modelo se ajusta mejor en conjunto "
        "a toda la validación.",
    "Dispersión por variable y modelo (análisis múltiple)": "Del módulo de "
        "análisis múltiple/en paralelo: un panel de dispersión (bisectriz "
        "1:1) por cada variable analizada (p. ej. caudal y varios "
        "piezómetros), con todos los modelos superpuestos y el mismo color "
        "para un modelo dado en todos los paneles. Permite ver de un "
        "vistazo, sin ir pestaña por pestaña, en qué variables ajusta mejor "
        "cada modelo y si ese desempeño es consistente entre ellas.",
    "Series observadas vs. calculadas por variable (análisis múltiple)":
        "Del módulo de análisis múltiple/en paralelo: un panel apilado por "
        "cada variable analizada, con la serie observada y cada modelo "
        "simulado superpuestos contra el mismo eje X. Equivale a ver, en "
        "una sola figura, el hidrograma/serie de todas las variables "
        "instrumentadas (caudal, piezómetros...) frente a los modelos "
        "comparados.",
    "Tabla resumen de métodos de validación utilizados": "Tabla representativa "
        "(estilo académico) de los métodos estadísticos de validación "
        "seleccionados en esta corrida: qué mide cada uno, su fórmula, su "
        "rango/valor óptimo y la referencia bibliográfica — un resumen de "
        "consulta rápida de \"qué se usó y por qué\", pensado para incluirse "
        "tal cual en el informe o la tesis, igual que un gráfico más.",
}
