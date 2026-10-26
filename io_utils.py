"""
io_utils.py
-----------
Carga y validación de series de tiempo (fecha, observado, una o más
series simuladas) desde archivos CSV o Excel (.xlsx/.xls/.xlsm), en
reemplazo de la hoja "Input" / botón "Input" de CT_2010.xlsm.

El archivo de entrada debe tener, como mínimo, una columna de fecha,
una columna de caudal/variable observada y una o más columnas de
caudal/variable simulada. El usuario elige qué columnas cumplen cada
rol desde la interfaz gráfica.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SUPPORTED_EXCEL = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_TEXT = {".csv", ".txt", ".tsv"}


def list_sheets(path: str | Path) -> list[str]:
    """Devuelve los nombres de las hojas de un archivo Excel."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXCEL:
        return []
    xls = pd.ExcelFile(path)
    return xls.sheet_names


def read_table(path: str | Path, sheet_name=None) -> pd.DataFrame:
    """Lee un archivo CSV/TSV o una hoja de Excel a un DataFrame crudo
    (sin procesar fechas ni tipos), preservando encabezados tal cual
    están en el archivo."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in SUPPORTED_EXCEL:
        df = pd.read_excel(path, sheet_name=sheet_name or 0, engine=None)
    elif suffix in SUPPORTED_TEXT:
        sep = "\t" if suffix == ".tsv" else None
        df = pd.read_csv(path, sep=sep, engine="python")
    else:
        raise ValueError(f"Formato de archivo no soportado: {suffix}")

    return df


def looks_like_date_column(series: pd.Series, min_fraction: float = 0.9) -> bool:
    """¿Esta columna es realmente una fecha/hora? True si ya es de tipo
    fecha, o si es texto y al menos `min_fraction` de sus valores se
    interpreta como fecha. Una columna puramente numérica (p. ej.
    profundidad 1, 2, 3...) NO cuenta: pandas la convertiría en
    "fechas" de 1970, y eso haría correr el análisis de extremos con
    datos que no son una serie de tiempo."""
    if series is None or len(series) == 0:
        return False
    if pd.api.types.is_datetime64_any_dtype(series):
        return bool(series.notna().sum() >= 2)
    if pd.api.types.is_numeric_dtype(series):
        return False
    s = series.dropna()
    if len(s) < 2:
        return False
    # texto que en realidad es un número ("12.5") no es una fecha
    if pd.to_numeric(s, errors="coerce").notna().mean() > 0.5:
        return False
    parsed = pd.to_datetime(s, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= min_fraction)


def build_timeseries(df: pd.DataFrame, date_col: str, obs_col: str,
                      sim_cols: list[str]) -> pd.DataFrame:
    """A partir de un DataFrame crudo y los nombres de columna
    elegidos por el usuario, arma una serie de tiempo limpia: fecha
    como índice datetime ordenado, columnas numéricas, sin filas
    totalmente vacías.

    Equivalente a lo que hacía el botón "Input" del VBA (pegar la
    serie ingresada en la hoja "Source" y recalcular estadísticas),
    pero de forma genérica para cualquier archivo de entrada.
    """
    cols = [date_col, obs_col] + list(sim_cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Columnas no encontradas en el archivo: {missing}")

    out = df[cols].copy()
    out.columns = ["Fecha", "Observado"] + list(sim_cols)

    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce", format="mixed")
    for c in ["Observado"] + list(sim_cols):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["Fecha"]).sort_values("Fecha")
    out = out.dropna(subset=["Observado"], how="all")
    out = out.reset_index(drop=True)
    return out


def build_validation_dataset(df: pd.DataFrame, obs_col: str,
                              sim_cols: list[str],
                              x_col: str | None = None) -> pd.DataFrame:
    """Igual que `build_timeseries`, pero SIN exigir una columna de
    fecha/eje X: solo arma la tabla numérica limpia (Observado +
    simuladas) que necesita la pestaña «Validación».

    Existe para que el análisis de bondad de ajuste (indicadores
    estadísticos) funcione también con datos que no son series de
    tiempo hidrológicas — por ejemplo, en geotecnia o estructuras,
    donde el eje independiente puede ser profundidad, distancia u
    otra variable, no una fecha. El hidrograma y el análisis de
    extremos (POT) sí necesitan una columna de fecha real y usan
    `build_timeseries` en su lugar.

    Si se pasa `x_col` (el "Eje X" elegido, exista o no una fecha
    real), su valor crudo se conserva en la columna "_EjeX" -- sin
    intentar interpretarlo como fecha -- para que el gráfico general
    de comparación pueda usarlo como eje independiente (p. ej.
    profundidad) en vez de solo el número de fila.
    """
    cols = [obs_col] + list(sim_cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Columnas no encontradas en el archivo: {missing}")

    out = df[cols].copy()
    out.columns = ["Observado"] + list(sim_cols)
    for c in ["Observado"] + list(sim_cols):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    if x_col and x_col in df.columns and x_col not in cols:
        out["_EjeX"] = df[x_col].to_numpy()

    out = out.dropna(subset=["Observado"], how="all")
    out = out.reset_index(drop=True)
    return out


def infer_years_of_record(fechas: pd.Series) -> float:
    """Duración del registro en años (365.25 días/año), tal como se
    calcula en Calculations!Y2 / AD2 del Excel original:
    ROUND((max(fecha)-min(fecha))/365.25, 0)."""
    span_days = (fechas.max() - fechas.min()).days
    return round(span_days / 365.25)
