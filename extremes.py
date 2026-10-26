"""
extremes.py
-----------
Análisis de valores extremos (POT - "Peaks Over Threshold") y
transformación Box-Cox, replicando la lógica de las hojas
"Calculations" y "Bissector" de CT_2010.xlsm (metodología basada en
WETSPRO, Willems, 2000/2009).

En la planilla original, los eventos independientes (picos de
crecida / estiajes) se identificaban con un programa externo
(WETSPRO) y se copiaban a mano a las columnas I,J,K,... de la hoja
"Calculations". Aquí se automatiza esa selección de picos con un
criterio de independencia estándar (separación mínima entre eventos,
scipy.signal.find_peaks), manteniendo el resto de la metodología:

  1. Selección de picos independientes por encima/debajo de un
     umbral, con separación temporal mínima.
  2. Para cada evento observado se define una "ventana" (celdas
     K+1:L de la hoja Calculations) y se extrae el máximo/mínimo de
     cada serie simulada dentro de esa misma ventana -> series de
     eventos extremos sincronizados observado-simulado.
  3. Periodo de retorno empírico: T = N_años / rango (posición de
     graficación tipo Weibull sobre la serie de picos, columnas
     W:Y y AB:AD de "Calculations").
  4. Transformación Box-Cox de los máximos, y Box-Cox del recíproco
     (1/x) para los mínimos (estabiliza varianza en estiajes),
     columnas AP:BJ de "Calculations".
  5. Estadísticas de error entre extremos observados y simulados
     (media, desviación estándar, eficiencia EF) en la escala
     original y en la escala Box-Cox.

Referencias
-----------
Willems, P. (2000). "Compound Intensity/Duration/Frequency-relationships
of extreme precipitation for two seasons and two storm types".
Journal of Hydrology.

Willems, P. (2009). "A time series tool to support the multi-criteria
performance evaluation of rainfall-runoff models". Environmental
Modelling & Software, 24(3), 311-321. (WETSPRO)

Box, G.E.P. & Cox, D.R. (1964). "An analysis of transformations".
Journal of the Royal Statistical Society, Series B.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy import stats as sstats


@dataclass
class POTResult:
    kind: str                       # "max" o "min"
    dates: np.ndarray               # fecha representativa de cada evento
    obs: np.ndarray                 # valor observado del evento (máx/mín en ventana)
    sim: dict                       # {nombre_corrida: array de valores simulados del evento}
    rank: np.ndarray                # rango 1..N (1 = evento más extremo)
    return_period: np.ndarray       # T [años]
    years_of_record: float


def _event_windows(peak_idx: np.ndarray, n: int) -> list[tuple[int, int]]:
    """Dado un arreglo de índices de picos (ordenados temporalmente),
    define para cada uno una ventana [inicio, fin] cuyo punto medio
    cae a mitad de camino con los eventos vecinos (equivalente a las
    columnas K:L de "Calculations": desde el pico anterior+1 hasta el
    inicio del siguiente pico)."""
    windows = []
    for i, p in enumerate(peak_idx):
        start = 0 if i == 0 else (peak_idx[i - 1] + p) // 2 + 1
        end = n - 1 if i == len(peak_idx) - 1 else (p + peak_idx[i + 1]) // 2
        windows.append((start, end))
    return windows


def select_pot_events(df: pd.DataFrame, date_col: str, obs_col: str,
                       sim_cols: list[str], kind: str = "max",
                       threshold: float | None = None,
                       threshold_quantile: float = 0.98,
                       min_separation_days: int = 10,
                       max_events: int = 150) -> POTResult:
    """Selecciona eventos extremos independientes (máximos o mínimos)
    de la serie observada y extrae los valores correspondientes de
    cada serie simulada en la misma ventana temporal.

    Parameters
    ----------
    kind : "max" (crecidas) o "min" (estiajes / caudales bajos).
    threshold : umbral fijo; si es None se usa el cuantil
        `threshold_quantile` de la serie observada (0.98 para
        máximos, y automáticamente 1-threshold_quantile para
        mínimos).
    min_separation_days : separación mínima en días entre eventos
        independientes (criterio de independencia, análogo al usado
        en WETSPRO).
    max_events : límite superior de eventos a conservar (la planilla
        original limitaba a 150 POTs).
    """
    dates = pd.to_datetime(df[date_col]).to_numpy()
    obs = df[obs_col].to_numpy(dtype=float)
    n = len(obs)

    # Paso temporal típico (en días) para convertir la separación
    # mínima de días a número de muestras.
    dt_days = np.median(np.diff(dates).astype("timedelta64[D]").astype(float))
    dt_days = dt_days if dt_days > 0 else 1.0
    distance = max(1, int(round(min_separation_days / dt_days)))

    if kind == "max":
        series_for_peaks = obs
        q = threshold_quantile
    elif kind == "min":
        series_for_peaks = -obs
        q = threshold_quantile  # se interpreta sobre la serie invertida
    else:
        raise ValueError("kind debe ser 'max' o 'min'")

    if threshold is None:
        thr = np.nanquantile(series_for_peaks, q)
    else:
        thr = threshold if kind == "max" else -threshold

    peak_idx, _ = find_peaks(series_for_peaks, height=thr, distance=distance)

    if peak_idx.size == 0:
        raise ValueError(
            "No se identificaron eventos extremos con los parámetros "
            "actuales; reduzca el umbral o la separación mínima."
        )

    if peak_idx.size > max_events:
        # Conservar los eventos más extremos si se supera el límite.
        vals = series_for_peaks[peak_idx]
        keep = np.argsort(vals)[::-1][:max_events]
        peak_idx = np.sort(peak_idx[keep])

    windows = _event_windows(peak_idx, n)

    event_dates, event_obs = [], []
    event_sim = {c: [] for c in sim_cols}
    for (start, end), p in zip(windows, peak_idx):
        seg_obs = obs[start:end + 1]
        if kind == "max":
            event_obs.append(np.nanmax(seg_obs))
        else:
            event_obs.append(np.nanmin(seg_obs))
        event_dates.append(dates[p])
        for c in sim_cols:
            seg_sim = df[c].to_numpy(dtype=float)[start:end + 1]
            event_sim[c].append(np.nanmax(seg_sim) if kind == "max" else np.nanmin(seg_sim))

    event_obs = np.array(event_obs, dtype=float)
    event_dates = np.array(event_dates)
    for c in sim_cols:
        event_sim[c] = np.array(event_sim[c], dtype=float)

    years = (pd.Timestamp(dates.max()) - pd.Timestamp(dates.min())).days / 365.25

    # Orden y periodo de retorno (posición de graficación T=N_años/rango)
    order = np.argsort(event_obs)[::-1] if kind == "max" else np.argsort(event_obs)
    rank = np.arange(1, len(event_obs) + 1)
    return_period = years / rank

    return POTResult(
        kind=kind,
        dates=event_dates[order],
        obs=event_obs[order],
        sim={c: event_sim[c][order] for c in sim_cols},
        rank=rank,
        return_period=return_period,
        years_of_record=years,
    )


# ---------------------------------------------------------------------
# Transformación Box-Cox
# ---------------------------------------------------------------------

def boxcox_transform(x: np.ndarray, lam: float | None = None) -> tuple[np.ndarray, float]:
    """Transformación Box-Cox estándar y = (x^lambda - 1)/lambda
    (y = ln(x) si lambda=0). Si `lam` es None, se estima por máxima
    verosimilitud (normalidad) con scipy.stats.boxcox.
    Devuelve (y, lambda_usado)."""
    x = np.asarray(x, dtype=float)
    if np.any(x <= 0):
        raise ValueError(
            "Box-Cox requiere valores estrictamente positivos (hay un evento "
            "extremo con valor 0 o negativo)."
        )
    if lam is None:
        try:
            y, lam = sstats.boxcox(x)
        except ValueError as exc:
            if "constant" in str(exc).lower():
                raise ValueError(
                    "los eventos extremos seleccionados son todos iguales (o "
                    "casi) entre sí, así que no hay variación para ajustar la "
                    "transformación Box-Cox. Suele pasar con pocos eventos, o "
                    "cuando el umbral/separación mínima deja eventos repetidos "
                    "(por ejemplo, varios estiajes con el mismo valor mínimo "
                    "de sensor). Pruebe con un umbral distinto, más años de "
                    "datos, o una separación mínima menor."
                ) from exc
            raise
        return y, float(lam)
    if abs(lam) < 1e-8:
        return np.log(x), 0.0
    return (x ** lam - 1) / lam, float(lam)


def boxcox_reciprocal_transform(x: np.ndarray, lam: float | None = None) -> tuple[np.ndarray, float]:
    """Transformación Box-Cox aplicada al recíproco (1/x), tal como
    se usa en la planilla original para estabilizar la varianza de
    los caudales mínimos / estiajes (columnas BB:BJ de
    "Calculations"). Devuelve (y, lambda_usado)."""
    return boxcox_transform(1.0 / np.asarray(x, dtype=float), lam=lam)


# ---------------------------------------------------------------------
# Estadísticas de error entre extremos observados y simulados
# ---------------------------------------------------------------------

def extreme_error_stats(obs_extreme: np.ndarray, sim_extreme: np.ndarray) -> dict:
    """Error medio, desviación estándar del error y eficiencia (EF,
    misma fórmula de Nash-Sutcliffe) entre una serie de eventos
    extremos observados y simulados ya sincronizados (mismo orden /
    misma ventana), equivalente a las columnas AN:AO (máximos) y
    AZ:BA (mínimos) de "Calculations"."""
    obs_extreme = np.asarray(obs_extreme, dtype=float)
    sim_extreme = np.asarray(sim_extreme, dtype=float)
    err = sim_extreme - obs_extreme
    me = err.mean()
    std = err.std(ddof=1) if len(err) > 1 else np.nan
    ss_res = np.sum((obs_extreme - sim_extreme) ** 2)
    ss_tot = np.sum((obs_extreme - obs_extreme.mean()) ** 2)
    ef = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"Error medio": me, "STD del error": std, "EF": ef}


def full_extreme_analysis(pot_result: POTResult, lam_override: float | None = None) -> dict:
    """Arma el análisis completo de un `POTResult`: transforma a
    Box-Cox (o Box-Cox recíproco si kind == 'min'), calcula lambda
    óptimo sobre la serie observada, aplica ese mismo lambda a las
    simulaciones, y calcula estadísticas de error en ambas escalas
    (original y Box-Cox) para cada corrida simulada."""
    if pot_result.kind == "max":
        obs_bc, lam = boxcox_transform(pot_result.obs, lam=lam_override)
        transform = lambda x: boxcox_transform(x, lam=lam)[0]
    else:
        obs_bc, lam = boxcox_reciprocal_transform(pot_result.obs, lam=lam_override)
        transform = lambda x: boxcox_reciprocal_transform(x, lam=lam)[0]

    results = {"lambda": lam, "por_corrida": {}}
    for name, sim_vals in pot_result.sim.items():
        sim_bc = transform(sim_vals)
        raw_stats = extreme_error_stats(pot_result.obs, sim_vals)
        bc_stats = extreme_error_stats(obs_bc, sim_bc)
        results["por_corrida"][name] = {
            "original": raw_stats,
            "box_cox": bc_stats,
            "sim_bc": sim_bc,
        }
    results["obs_bc"] = obs_bc
    return results
