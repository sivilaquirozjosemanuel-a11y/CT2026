"""
stats.py
--------
Indicadores estadísticos de bondad de ajuste entre una serie observada
(Oi) y una serie simulada (Pi), replicando exactamente las fórmulas de
las hojas "Statistics", "Stats 1" y "Stats 2" de CT_2010.xlsm, más
algunos indicadores adicionales de uso estándar en hidrología (PBIAS,
KGE) que no estaban en la planilla original pero se incluyen como
referencia complementaria.

Todas las funciones trabajan con arreglos de numpy (o pandas Series)
sin valores NaN: usar `align_series` para sincronizar y limpiar antes
de calcular.

Referencias
-----------
Vázquez, R.F. (2003). "Assessment of the performance of physically
based distributed codes simulating medium size hydrological
systems". PhD thesis / publications, UNESCO-IHE.

Mertens, B. (2003). Trabajo relacionado a la desviación estándar de
los residuos como criterio de calibración.

Willmott, C.J. (1981). "On the validation of models". Physical
Geography, 2(2), 184-194. (Índice de concordancia / "Model Skill").

Nash, J.E. & Sutcliffe, J.V. (1970). "River flow forecasting through
conceptual models part I — A discussion of principles". Journal of
Hydrology, 10(3), 282-290. (Eficiencia EF / NSE).

Gupta, H.V., Kling, H., Yilmaz, K.K., Martinez, G.F. (2009).
"Decomposition of the mean squared error and NSE performance
criteria". Journal of Hydrology, 377(1-2), 80-91. (KGE, adicional).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS_DEFAULT = 0.001  # 'e' en la hoja Excel (celda E2), evita ln(0)


def align_series(obs, sim) -> tuple[np.ndarray, np.ndarray]:
    """Convierte a arreglos numpy y elimina pares con NaN en cualquiera
    de las dos series, preservando la correspondencia índice a índice."""
    o = pd.Series(obs).astype(float)
    p = pd.Series(sim).astype(float)
    df = pd.concat([o, p], axis=1, keys=["o", "p"]).dropna()
    return df["o"].to_numpy(), df["p"].to_numpy()


def goodness_of_fit_detailed(obs, sim, eps: float = EPS_DEFAULT, k: int = 0) -> dict:
    """Igual que `goodness_of_fit`, pero además de los indicadores
    finales devuelve, bajo la clave "_detalle", todos los valores
    intermedios (escalares) usados para calcularlos: n, promedios,
    sumas de cuadrados, covarianza, etc. Esto permite mostrar "el paso
    del cálculo" (con qué datos se trabajó, los cálculos intermedios y
    el resultado final) en la interfaz y en los reportes, en vez de
    solo el resultado.

    `k` es el número de parámetros/variables independientes
    calibrados, usado únicamente por el SEE de auscultación de presas
    (grados de libertad = n − k − 1). Por defecto k=0 (equivalente a
    no descontar grados de libertad adicionales).
    """
    Oi, Pi = align_series(obs, sim)
    n = Oi.size
    if n < 2:
        raise ValueError("Se requieren al menos 2 pares de datos válidos.")

    avg_o = Oi.mean()
    avg_p = Pi.mean()

    resid = Pi - Oi                      # Pi - Oi
    sq_resid = resid ** 2                 # (Pi-Oi)^2
    abs_resid = np.abs(resid)             # |Pi-Oi|

    dev_o = Oi - avg_o                    # Oi - Avg(Oi)
    dev_p = Pi - avg_p                    # Pi - Avg(Pi)
    dev_p_from_o = Pi - avg_o             # Pi - Avg(Oi)

    ss_o = np.sum(dev_o ** 2)             # Sum((Oi-Avg Oi)^2)
    ss_p_from_o = np.sum(dev_p_from_o ** 2)   # Sum((Pi-Avg Oi)^2)
    ss_p = np.sum(dev_p ** 2)             # Sum((Pi-Avg Pi)^2)
    ss_res = np.sum(sq_resid)             # Sum((Pi-Oi)^2)
    cov_op = np.sum(dev_o * dev_p)        # Sum((Oi-AvgOi)(Pi-AvgPi))
    sum_abs_resid = np.sum(abs_resid)
    sum_resid = np.sum(resid)
    sum_o = np.sum(Oi)

    # --- Statistics sheet (Vázquez 2003 / Mertens 2003) ------------
    MAE = sum_abs_resid / n
    STD = np.sqrt(np.sum((resid - resid.mean()) ** 2) / (n - 1))
    RMSE = np.sqrt(ss_res / n)
    EF = (ss_o - ss_res) / ss_o                       # Nash-Sutcliffe
    CD = ss_o / ss_p_from_o                            # Coef. de determinación (def. Vázquez)
    R = cov_op / (np.sqrt(ss_o) * np.sqrt(ss_p))       # Correlación lineal (Pearson)

    # --- Model Skill (Willmott, 1981) -------------------------------
    willmott_denom = np.sum((np.abs(dev_p_from_o) + np.abs(dev_o)) ** 2)
    model_skill = 1 - ss_res / willmott_denom

    # --- Criterios adicionales CR1, CR4, CR5 ------------------------
    CR1 = avg_p / avg_o - 1                            # Sesgo del modelo

    ln_o = np.log(Oi + eps)
    ln_p = np.log(Pi + eps)
    ln_avg_o = np.log(avg_o + eps)
    num_cr4 = np.sum((ln_p - ln_o) ** 2)
    den_cr4 = np.sum((ln_o - ln_avg_o) ** 2)
    CR4 = 1 - num_cr4 / den_cr4                         # NS de logaritmos (caudales bajos)

    num_cr5 = np.sum((Oi + avg_o) * sq_resid)
    den_cr5 = np.sum((Oi + avg_o) * (dev_o ** 2))
    CR5 = 1 - num_cr5 / den_cr5                          # NS "adaptado" (pesa altos y bajos)

    # --- Indicadores adicionales (no en la planilla original) -------
    PBIAS = 100.0 * sum_resid / sum_o                    # Sesgo porcentual (%)
    r_pearson = np.corrcoef(Oi, Pi)[0, 1]
    beta = avg_p / avg_o
    gamma = (Pi.std(ddof=0) / avg_p) / (Oi.std(ddof=0) / avg_o)
    KGE = 1 - np.sqrt((r_pearson - 1) ** 2 + (beta - 1) ** 2 + (gamma - 1) ** 2)

    # --- RSR (Moriasi et al., 2007) y criterio MAE/STD (Singh et al., --
    # --- 2004; Moriasi et al., 2007) --------------------------------
    std_o = np.sqrt(ss_o / n)                            # σ observado (población, /n, consistente con RMSE)
    RSR = RMSE / std_o if std_o > 0 else float("nan")
    MAE_STD = MAE / std_o if std_o > 0 else float("nan")

    # --- SEE de auscultación de presas (Salazar et al., 2017) -------
    dof = max(n - k - 1, 1)
    SEE = np.sqrt(ss_res / dof)
    if SEE > 0:
        n_within_2see = int(np.sum(abs_resid <= 2 * SEE))
        n_within_3see = int(np.sum(abs_resid <= 3 * SEE))
    else:
        n_within_2see = n
        n_within_3see = n
    pct_within_2see = 100.0 * n_within_2see / n
    pct_within_3see = 100.0 * n_within_3see / n
    n_anomalos = n - n_within_3see

    finales = {
        "n": int(n),
        "Avg(Oi)": avg_o,
        "Avg(Pi)": avg_p,
        "MAE": MAE,
        "STD": STD,
        "RMSE": RMSE,
        "EF": EF,
        "CD": CD,
        "R": R,
        "Model Skill (Willmott)": model_skill,
        "CR1 (Sesgo del modelo)": CR1,
        "CR4 (NS logarítmico)": CR4,
        "CR5 (NS adaptado)": CR5,
        "PBIAS (%)": PBIAS,
        "KGE": KGE,
        "RSR": RSR,
        "MAE/STD(Oi)": MAE_STD,
        "SEE (Auscultación de presas)": SEE,
        "% dentro de ±2·SEE": pct_within_2see,
    }

    detalle = {
        "n": int(n),
        "k": int(k),
        "eps": eps,
        "avg_o": avg_o,
        "avg_p": avg_p,
        "sum_o": sum_o,
        "sum_abs_resid": sum_abs_resid,
        "sum_resid": sum_resid,
        "ss_o": ss_o,
        "ss_p": ss_p,
        "ss_p_from_o": ss_p_from_o,
        "ss_res": ss_res,
        "cov_op": cov_op,
        "willmott_denom": willmott_denom,
        "ln_avg_o": ln_avg_o,
        "num_cr4": num_cr4,
        "den_cr4": den_cr4,
        "num_cr5": num_cr5,
        "den_cr5": den_cr5,
        "r_pearson": r_pearson,
        "beta": beta,
        "gamma": gamma,
        "std_o": std_o,
        "dof": int(dof),
        "n_within_2see": n_within_2see,
        "n_within_3see": n_within_3see,
        "pct_within_2see": pct_within_2see,
        "pct_within_3see": pct_within_3see,
        "n_anomalos": n_anomalos,
    }

    out = dict(finales)
    out["_detalle"] = detalle
    return out


def goodness_of_fit(obs, sim, eps: float = EPS_DEFAULT, k: int = 0) -> dict:
    """Calcula todos los indicadores de la planilla CT_2010 (más los
    indicadores adicionales de auscultación/desempeño incorporados
    posteriormente) para un par de series (observada, simulada).

    Devuelve un diccionario con los mismos nombres usados en la hoja
    "Statistics" / "Stats 1" / "Stats 2" del Excel original, más
    "RSR", "MAE/STD(Oi)", "SEE (Auscultación de presas)" y
    "% dentro de ±2·SEE". Es un envoltorio delgado sobre
    `goodness_of_fit_detailed`, que además expone los cálculos
    intermedios bajo la clave "_detalle" para quien los necesite (ver
    `calculation_trace`)."""
    full = goodness_of_fit_detailed(obs, sim, eps=eps, k=k)
    full.pop("_detalle", None)
    return full


# Rangos de referencia (min, max, óptimo) y descripción corta, tal
# como figuran en la hoja "Statistics" del Excel (Vázquez, 2003).
CRITERIA_REFERENCE = {
    "MAE": dict(sheet=True, min=0, max="+", best=0, ref="Vázquez, 2003",
                desc="Error medio absoluto"),
    "STD": dict(sheet=True, min=0, max="+", best=0, ref="Mertens, 2003",
                desc="Desviación estándar de los residuos"),
    "RMSE": dict(sheet=True, min=0, max="+", best=0, ref="Vázquez, 2003",
                 desc="Raíz del error cuadrático medio"),
    "EF": dict(sheet=True, min="-inf", max=1, best=1, ref="Nash & Sutcliffe, 1970",
               desc="Eficiencia de Nash-Sutcliffe"),
    "CD": dict(sheet=True, min=0, max="+", best=1, ref="Vázquez, 2003",
               desc="Coeficiente de determinación"),
    "R": dict(sheet=True, min=0, max=1, best=1, ref="Vázquez, 2003",
              desc="Bondad de ajuste lineal (correlación)"),
    "Model Skill (Willmott)": dict(min=0, max=1, best=1, ref="Willmott, 1981",
                                    desc="Índice de concordancia"),
    "CR1 (Sesgo del modelo)": dict(min="-", max="+", best=0, ref="Vázquez, 2003",
                                    desc="Sesgo relativo del modelo"),
    "CR4 (NS logarítmico)": dict(min="-inf", max=1, best=1, ref="Vázquez, 2003",
                                  desc="NS aplicado a logaritmos (realza caudales bajos)"),
    "CR5 (NS adaptado)": dict(min="-inf", max=1, best=1, ref="Vázquez, 2003",
                               desc="NS ponderado (realza caudales altos y bajos)"),
    "PBIAS (%)": dict(min="-", max="+", best=0, ref="Gupta et al., 1999",
                       desc="Sesgo porcentual del volumen"),
    "KGE": dict(min="-inf", max=1, best=1, ref="Gupta et al., 2009",
                desc="Eficiencia de Kling-Gupta"),
    "RSR": dict(min=0, max="+", best=0, ref="Moriasi et al., 2007",
                desc="RMSE normalizado por la desviación estándar observada"),
    "MAE/STD(Oi)": dict(min=0, max="+", best=0, ref="Singh et al., 2004 / Moriasi et al., 2007",
                         desc="Error medio absoluto en relación a la variabilidad observada"),
    "SEE (Auscultación de presas)": dict(min=0, max="+", best=0, ref="Salazar et al., 2017",
                                          desc="Error estándar de estimación (modelos de auscultación, tipo HST)"),
    "% dentro de ±2·SEE": dict(min=0, max=100, best=100, ref="Salazar et al., 2017",
                                desc="Porcentaje de lecturas dentro de la banda de comportamiento esperado (±2·SEE)"),
}


# -----------------------------------------------------------------------
# Contenido didáctico: fórmula y explicación de cada indicador, para
# mostrar "el cálculo" y no solo el resultado en la interfaz y en los
# reportes (pedido explícito de la usuaria: que se vea más el proceso).
# -----------------------------------------------------------------------
INDICATOR_HELP = {
    "MAE": dict(
        formula="MAE = (1/n) · Σ |Pi − Oi|",
        como_leerlo="Promedio del valor absoluto de los residuos (simulado "
                     "menos observado). Está en las mismas unidades que el "
                     "caudal, así que un MAE de 2 significa que, en promedio, "
                     "el modelo se equivoca por 2 m3/s. Cuanto más chico, mejor.",
        teoria="El Error Medio Absoluto es el indicador de error más simple "
               "e intuitivo en hidrología: promedia, sin importar el signo, "
               "cuánto se aleja cada valor simulado del observado. A "
               "diferencia del RMSE, no penaliza más los errores grandes que "
               "los pequeños (es lineal), por lo que es menos sensible a "
               "unos pocos picos mal simulados y refleja mejor el \"error "
               "típico\" del modelo a lo largo de todo el periodo. Se usa "
               "junto con RMSE para saber si el error está concentrado en "
               "pocos eventos (RMSE mucho mayor que MAE) o distribuido de forma pareja "
               "(RMSE cercano a MAE). (Vázquez, 2003)",
        pasos=[
            "Para cada instante i se calcula el residuo ei = Pi − Oi "
            "(simulado menos observado).",
            "Se toma el valor absoluto de cada residuo, |ei|, para que los "
            "errores positivos y negativos no se cancelen entre sí.",
            "Se promedian los n valores absolutos: MAE = (1/n)·Σ|ei|.",
            "El resultado queda en las mismas unidades que la variable "
            "comparada (p. ej. m3/s).",
        ]),
    "STD": dict(
        formula="STD = √( Σ (ei − μe)^2 / (n−1) ),  con ei = Pi − Oi",
        como_leerlo="Desviación estándar de los residuos: qué tan dispersos "
                     "están los errores alrededor de su propio promedio (μe). "
                     "Un STD chico indica un error consistente (aunque exista "
                     "sesgo); un STD grande indica que el modelo a veces "
                     "acierta mucho y a veces falla mucho.",
        teoria="La desviación estándar de los residuos mide la dispersión "
               "del error alrededor de su propio promedio (no alrededor de "
               "cero), es decir, qué tan consistente es el error del "
               "modelo. Un modelo puede tener un sesgo constante (por "
               "ejemplo, subestimar siempre en 1 m3/s) y aun así tener un "
               "STD bajo, porque el error no varía mucho de un instante a "
               "otro; ese sesgo se detecta con CR1/PBIAS, no con STD. Se "
               "usa como criterio complementario de calibración para "
               "distinguir \"error sistemático\" de \"error errático\". "
               "(Mertens, 2003)",
        pasos=[
            "Se calculan los residuos ei = Pi − Oi para cada instante.",
            "Se calcula el promedio de los residuos, μe = (1/n)·Σei (el "
            "sesgo medio del modelo).",
            "Se mide cuánto se aleja cada residuo de ese promedio: "
            "(ei − μe)^2.",
            "Se suman esas desviaciones al cuadrado, se dividen entre "
            "(n−1) (varianza muestral) y se toma la raíz cuadrada: "
            "STD = √[Σ(ei−μe)^2/(n−1)].",
        ]),
    "RMSE": dict(
        formula="RMSE = √( (1/n) · Σ (Pi − Oi)^2 )",
        como_leerlo="Como el MAE, pero al elevar al cuadrado penaliza más "
                     "los errores grandes (picos de crecida mal simulados "
                     "pesan más que pequeños desvíos en estiaje). Siempre "
                     "RMSE ≥ MAE.",
        teoria="La raíz del error cuadrático medio también resume el error "
               "típico del modelo, pero al elevar cada residuo al cuadrado "
               "antes de promediar, los errores grandes (picos de crecida "
               "mal simulados) pesan mucho más que muchos errores pequeños. "
               "Por eso RMSE ≥ MAE siempre, y la diferencia entre ambos es "
               "un diagnóstico útil: si RMSE es mucho mayor que MAE, el "
               "error del modelo está concentrado en pocos eventos extremos "
               "más que distribuido de forma pareja. (Vázquez, 2003)",
        pasos=[
            "Se calculan los residuos ei = Pi − Oi.",
            "Se eleva cada residuo al cuadrado, ei^2, para que todos los "
            "términos sean positivos y los errores grandes pesen "
            "desproporcionadamente más.",
            "Se promedian los n valores: (1/n)·Σei^2.",
            "Se toma la raíz cuadrada para volver a las unidades "
            "originales: RMSE = √[(1/n)·Σei^2].",
        ]),
    "EF": dict(
        formula="EF = 1 − [ Σ(Oi−Pi)^2 / Σ(Oi−μO)^2 ]",
        como_leerlo="Eficiencia de Nash-Sutcliffe: compara el error del "
                     "modelo contra el error de usar simplemente el promedio "
                     "observado (μO) como predicción constante. EF=1 es ajuste "
                     "perfecto; EF=0 significa que el modelo es tan bueno "
                     "como usar el promedio; EF<0 significa que el promedio "
                     "predice mejor que el modelo.",
        teoria="La eficiencia de Nash-Sutcliffe (Nash & Sutcliffe, 1970) es "
               "el indicador más usado en modelación hidrológica para "
               "evaluar qué tan bien un modelo reproduce la serie "
               "observada, comparándolo contra el modelo más simple "
               "posible: predecir siempre el promedio observado. Es "
               "sensible sobre todo a los caudales altos (porque el "
               "denominador, la varianza observada, está dominado por los "
               "picos de crecida), por lo que un EF alto no garantiza que "
               "los estiajes estén bien simulados (para eso conviene "
               "revisar CR4).",
        pasos=[
            "Se calcula el error del modelo: la suma de los residuos al "
            "cuadrado, Σ(Oi−Pi)^2.",
            "Se calcula el error de la \"predicción ingenua\" (usar siempre "
            "el promedio observado μO): Σ(Oi−μO)^2.",
            "Se divide el error del modelo entre el error de la predicción "
            "ingenua: esa razón indica qué fracción del error \"ya existía\" "
            "incluso sin modelo.",
            "Se resta esa razón de 1: EF = 1 − [error del modelo / error "
            "de la predicción ingenua]. Si el modelo es mejor que el "
            "promedio, EF > 0; si es peor, EF < 0.",
        ]),
    "CD": dict(
        formula="CD = Σ(Oi−μO)^2 / Σ(Pi−μO)^2",
        como_leerlo="Coeficiente de determinación (definición de Vázquez): "
                     "compara la variabilidad observada contra la variabilidad "
                     "simulada alrededor del promedio observado. El óptimo es "
                     "1; valores muy por encima o por debajo de 1 indican que "
                     "el modelo sub- o sobre-estima la variabilidad real.",
        teoria="El coeficiente de determinación (en la definición usada por "
               "esta planilla, Vázquez 2003) compara la variabilidad de la "
               "serie simulada con la variabilidad de la serie observada, "
               "ambas medidas respecto del promedio observado. A diferencia "
               "del EF, no mide directamente el error punto a punto, sino "
               "si el modelo reproduce la magnitud de las fluctuaciones: un "
               "modelo \"plano\" (poco variable) da CD bajo, y un modelo "
               "demasiado errático da CD alto, aunque en ambos casos el "
               "ajuste punto a punto podría ser malo — por eso CD se "
               "interpreta siempre junto con EF y R, nunca solo.",
        pasos=[
            "Se calcula la variabilidad observada respecto de su propio "
            "promedio: Σ(Oi−μO)^2.",
            "Se calcula la variabilidad simulada, pero respecto del "
            "promedio OBSERVADO (no del simulado): Σ(Pi−μO)^2.",
            "Se divide la primera entre la segunda: "
            "CD = Σ(Oi−μO)^2 / Σ(Pi−μO)^2.",
            "Un CD cercano a 1 indica que la variabilidad simulada es "
            "similar a la observada; CD mucho mayor que 1 indica que el modelo varía "
            "menos de lo real; CD mucho menor que 1 indica que varía más de lo real.",
        ]),
    "R": dict(
        formula="R = Σ(Oi−μO)(Pi−μP) / [ √Σ(Oi−μO)^2 · √Σ(Pi−μP)^2 ]",
        como_leerlo="Correlación lineal de Pearson entre observado y "
                     "simulado: mide si ambas series suben y bajan juntas "
                     "(la forma), sin penalizar que estén desplazadas en "
                     "magnitud. R cercano a 1 = buena correlación; no "
                     "garantiza por sí solo que los valores absolutos "
                     "coincidan (para eso hay que mirar EF, CD y PBIAS).",
        teoria="El coeficiente de correlación de Pearson mide qué tan bien "
               "las dos series se mueven juntas en el tiempo (suben y "
               "bajan en los mismos momentos), sin importar si sus "
               "magnitudes coinciden. Es posible tener R muy alto y aun "
               "así un mal ajuste (por ejemplo, si el modelo sistemática"
               "mente sobreestima todos los caudales en un 50%, R seguiría "
               "siendo casi 1, pero EF y PBIAS mostrarían el problema). Por "
               "eso R se usa para evaluar la \"forma\" del hidrograma, y "
               "siempre junto con indicadores de sesgo (CR1, PBIAS) y de "
               "error absoluto (EF, RMSE).",
        pasos=[
            "Se calculan las desviaciones de cada serie respecto de su "
            "propio promedio: (Oi−μO) y (Pi−μP).",
            "Se multiplican esas desviaciones término a término y se "
            "suman: la covarianza, Σ(Oi−μO)(Pi−μP).",
            "Se calcula la raíz de la suma de cuadrados de cada desviación "
            "por separado: √Σ(Oi−μO)^2 y √Σ(Pi−μP)^2.",
            "Se divide la covarianza entre el producto de esas dos raíces: "
            "R = covarianza / (√Σ(Oi−μO)^2·√Σ(Pi−μP)^2). El resultado va de "
            "−1 a 1.",
        ]),
    "Model Skill (Willmott)": dict(
        formula="d = 1 − Σ(Pi−Oi)^2 / Σ( |Pi−μO| + |Oi−μO| )^2",
        como_leerlo="Índice de concordancia de Willmott (1981): parecido al "
                     "EF, pero el denominador es menos sensible a valores "
                     "atípicos aislados. Va de 0 a 1, óptimo en 1.",
        teoria="El índice de concordancia de Willmott (1981) fue propuesto "
               "como una alternativa al EF menos sensible a valores "
               "atípicos aislados: usa un denominador que suma las "
               "distancias absolutas (no al cuadrado) de cada serie "
               "respecto del promedio observado, lo que \"amortigua\" el "
               "efecto de uno o dos picos extremadamente mal simulados que "
               "en el EF podrían dominar todo el resultado. Es útil como "
               "segunda opinión cuando el EF de una corrida parece "
               "anormalmente bajo por un solo evento atípico.",
        pasos=[
            "Se calcula el error del modelo: Σ(Pi−Oi)^2 (igual que en EF).",
            "Se calcula, para cada instante, la suma de las distancias "
            "absolutas |Pi−μO| + |Oi−μO| respecto del promedio observado, "
            "y se eleva al cuadrado cada suma.",
            "Se suman esos términos: el denominador de Willmott, "
            "Σ(|Pi−μO|+|Oi−μO|)^2.",
            "Se calcula d = 1 − [error del modelo / denominador de "
            "Willmott], igual en espíritu al EF pero con un denominador "
            "más robusto a valores atípicos.",
        ]),
    "CR1 (Sesgo del modelo)": dict(
        formula="CR1 = μP / μO − 1",
        como_leerlo="Sesgo relativo del volumen simulado respecto del "
                     "observado. CR1=0 es ideal; CR1>0 indica que el modelo "
                     "sobreestima en promedio (simula más caudal del real); "
                     "CR1<0 indica que subestima.",
        teoria="CR1 mide el sesgo relativo del volumen total simulado "
               "respecto del observado: si el modelo, en promedio, genera "
               "más o menos caudal del real, independientemente de si "
               "acierta el \"momento\" en que ocurre cada crecida o "
               "estiaje. Es el indicador más directo de sobreestimación/"
               "subestimación sistemática, y suele ser lo primero que se "
               "revisa antes de mirar indicadores más sofisticados como EF "
               "o KGE, porque un sesgo de volumen grande generalmente "
               "indica un problema de calibración de parámetros (p. ej. "
               "coeficientes de escurrimiento) más que de forma del "
               "hidrograma.",
        pasos=[
            "Se calcula el promedio de la serie simulada, μP, y el "
            "promedio de la observada, μO.",
            "Se divide μP entre μO: esa razón indica cuántas veces más (o "
            "menos) volumen simula el modelo en promedio.",
            "Se resta 1: CR1 = μP/μO − 1. Un CR1 de 0.15 significa que el "
            "modelo simula, en promedio, 15% más caudal que el observado.",
        ]),
    "CR4 (NS logarítmico)": dict(
        formula="CR4 = 1 − Σ(ln Pi−ln Oi)^2 / Σ(ln Oi−ln μO)^2",
        como_leerlo="Igual que EF pero aplicado a los logaritmos de los "
                     "caudales, lo que le da mucho más peso relativo a los "
                     "caudales bajos (estiajes) que EF normal, que está "
                     "dominado por las crecidas.",
        teoria="CR4 aplica la misma lógica del EF pero sobre el logaritmo "
               "de los caudales, no sobre los caudales directamente. Tomar "
               "logaritmos \"comprime\" los valores altos y \"expande\" los "
               "valores bajos, así que este indicador le da mucho más peso "
               "relativo a qué tan bien se simulan los caudales de estiaje "
               "que el EF normal (que está dominado por las crecidas). Es "
               "el indicador recomendado cuando el objetivo del modelo "
               "incluye la gestión de sequías, caudal ecológico o "
               "abastecimiento en época seca.",
        pasos=[
            "Se toma el logaritmo de cada valor observado y simulado, "
            "sumando una constante pequeña ε (0.001) para evitar ln(0) en "
            "caudales muy bajos: ln(Oi+ε), ln(Pi+ε).",
            "Se calcula el error en escala logarítmica: "
            "Σ(ln Pi − ln Oi)^2.",
            "Se calcula la variabilidad observada en escala logarítmica "
            "respecto de su propio promedio logarítmico μ(ln O): "
            "Σ(ln Oi − μ(ln O))^2.",
            "Se aplica la misma fórmula del EF pero con estos términos "
            "logarítmicos: CR4 = 1 − [error log / variabilidad log].",
        ]),
    "CR5 (NS adaptado)": dict(
        formula="CR5 = 1 − Σ(Oi+μO)(Pi−Oi)^2 / Σ(Oi+μO)(Oi−μO)^2",
        como_leerlo="Variante de EF que pondera cada evento por (Oi+μO), lo "
                     "que realza tanto los caudales altos como los bajos "
                     "frente a los intermedios, buscando un balance entre "
                     "EF (dominado por crecidas) y CR4 (dominado por estiajes).",
        teoria="CR5 es una variante del EF que pondera cada instante por "
               "(Oi+μO), dando más importancia tanto a los caudales altos "
               "como a los caudales bajos frente a los caudales intermedios "
               "(a diferencia del EF normal, dominado solo por los altos, "
               "o del CR4, dominado por los bajos). Busca un balance entre "
               "ambos extremos del régimen hidrológico, y es útil cuando "
               "interesa un buen ajuste tanto en crecidas como en estiajes "
               "simultáneamente, sin sacrificar uno por el otro.",
        pasos=[
            "Se calcula, para cada instante, el peso (Oi+μO), que crece "
            "con la magnitud del caudal observado.",
            "Se pondera el error cuadrático de cada instante por ese peso: "
            "Σ(Oi+μO)(Pi−Oi)^2.",
            "Se pondera de la misma forma la variabilidad observada: "
            "Σ(Oi+μO)(Oi−μO)^2.",
            "Se aplica la fórmula del EF con estos términos ponderados: "
            "CR5 = 1 − [error ponderado / variabilidad ponderada].",
        ]),
    "PBIAS (%)": dict(
        formula="PBIAS = 100 · Σ(Pi−Oi) / ΣOi",
        como_leerlo="Sesgo porcentual del volumen total simulado respecto "
                     "del observado (equivalente a CR1 pero expresado en %). "
                     "Un valor de -8% significa que el modelo simula, en "
                     "total, 8% menos volumen que lo observado en el período. "
                     "|PBIAS| < 10% suele considerarse muy bueno en hidrología.",
        teoria="El sesgo porcentual (Gupta et al., 1999) expresa el mismo "
               "sesgo de volumen que CR1, pero en porcentaje, lo que lo "
               "hace más fácil de comunicar e interpretar directamente "
               "(\"el modelo simula 8% menos volumen que lo observado\"). Es "
               "uno de los indicadores estándar en los criterios de "
               "desempeño de modelos hidrológicos (junto con NSE/EF y "
               "RSR), con umbrales ampliamente citados en la literatura "
               "para clasificar el desempeño como muy bueno, bueno, "
               "satisfactorio o insatisfactorio.",
        pasos=[
            "Se calcula la suma de los residuos: Σ(Pi−Oi) (el \"exceso\" o "
            "\"déficit\" de volumen simulado acumulado en todo el periodo).",
            "Se calcula la suma de los caudales observados: ΣOi (el "
            "volumen observado total).",
            "Se divide la primera suma entre la segunda y se multiplica "
            "por 100: PBIAS = 100·Σ(Pi−Oi)/ΣOi.",
            "Un PBIAS negativo indica subestimación de volumen; positivo, "
            "sobreestimación.",
        ]),
    "KGE": dict(
        formula="KGE = 1 − √[ (r−1)^2 + (β−1)^2 + (γ−1)^2 ],  β=μP/μO,  γ=(σP/μP)/(σO/μO)",
        como_leerlo="Eficiencia de Kling-Gupta: descompone el error en tres "
                     "partes independientes — r (correlación/forma), β "
                     "(sesgo de volumen) y γ (sesgo de variabilidad) — para "
                     "diagnosticar EN QUÉ falla el modelo, no solo cuánto. "
                     "KGE=1 es ajuste perfecto en las tres componentes.",
        teoria="La eficiencia de Kling-Gupta (Gupta et al., 2009) fue "
               "propuesta para corregir una limitación conocida del EF: el "
               "EF puede mejorar artificialmente si el modelo subestima la "
               "variabilidad, porque el término de varianza queda "
               "\"escondido\" dentro de un solo número. KGE separa "
               "explícitamente el error en tres componentes independientes "
               "y del mismo peso: correlación (forma), sesgo de volumen (β) "
               "y sesgo de variabilidad (γ), lo que permite diagnosticar EN "
               "QUÉ aspecto específico falla el modelo, en vez de solo "
               "saber cuánto falla en total. Es uno de los indicadores más "
               "usados en publicaciones recientes de hidrología para "
               "reportar el desempeño de un modelo junto con o en lugar "
               "del EF.",
        pasos=[
            "Se calcula r: la correlación de Pearson entre observado y "
            "simulado (mide la forma del hidrograma).",
            "Se calcula β = μP/μO: la razón de sesgo de volumen (idéntico "
            "en espíritu a CR1+1).",
            "Se calcula γ = (σP/μP)/(σO/μO): la razón de los coeficientes "
            "de variación, que compara la variabilidad relativa de ambas "
            "series.",
            "Se combinan las tres distancias al valor ideal (todas "
            "deberían ser 1) como una distancia euclidiana: "
            "KGE = 1 − √[(r−1)^2 + (β−1)^2 + (γ−1)^2].",
        ]),
    "RSR": dict(
        formula="RSR = RMSE / σO,  con σO = √( Σ(Oi−μO)^2 / n )",
        como_leerlo="RMSE expresado como fracción de la variabilidad natural "
                     "de la serie observada (σO). Un RSR de 0.4 significa que "
                     "el error típico del modelo equivale al 40% de la "
                     "dispersión natural de los datos observados. RSR=0 es "
                     "ajuste perfecto; cuanto más bajo, mejor.",
        teoria="El RSR (RMSE-observations Standard deviation Ratio, Moriasi "
               "et al., 2007) resuelve una limitación práctica del RMSE: al "
               "estar en las unidades de la variable (m3/s, mm, etc.), un "
               "RMSE de \"2\" es bueno o malo según la magnitud típica de la "
               "variable, y no es directamente comparable entre estudios ni "
               "entre variables distintas (p. ej. caudal vs. piezómetros). "
               "El RSR normaliza el RMSE dividiéndolo entre la desviación "
               "estándar de la serie observada, dando un número adimensional "
               "comparable entre cuencas, variables y estudios. Moriasi et "
               "al. (2007) propusieron los umbrales de desempeño más citados "
               "en la literatura hidrológica para este indicador (0.50/0.60/"
               "0.70), habitualmente usados junto con NSE y PBIAS como el "
               "trío estándar de criterios de calibración/validación de "
               "modelos.",
        pasos=[
            "Se calcula el RMSE del modelo (ver ficha de RMSE): "
            "√[(1/n)·Σ(Pi−Oi)^2].",
            "Se calcula la desviación estándar de la serie observada "
            "respecto de su propio promedio: σO = √[(1/n)·Σ(Oi−μO)^2].",
            "Se divide el RMSE entre σO: RSR = RMSE/σO. El resultado no "
            "tiene unidades y es comparable entre variables distintas.",
            "Se interpreta como referencia: cuanto más cerca de 0, mejor. "
            "La aplicación no impone rangos de clasificación; Moriasi et al. "
            "(2007) sugieren ≤0.70 como desempeño satisfactorio.",
        ]),
    "MAE/STD(Oi)": dict(
        formula="MAE/STD(Oi) = MAE / σO,  con σO = √( Σ(Oi−μO)^2 / n )",
        como_leerlo="Compara el error medio absoluto del modelo contra la "
                     "variabilidad natural de la serie observada. Singh et "
                     "al. (2004) consideran satisfactorio un MAE menor o "
                     "igual a la mitad de σO (razón ≤ 0.5). Cuanto más bajo, "
                     "mejor: el error del modelo es pequeño comparado con lo "
                     "que la variable observada varía de por sí.",
        teoria="Este criterio, propuesto por Singh et al. (2004) y recogido "
               "también por Moriasi et al. (2007), responde a la misma "
               "necesidad que el RSR (normalizar el error para que sea "
               "comparable entre variables y estudios) pero usando el error "
               "medio absoluto (MAE) en vez del RMSE. Al no elevar los "
               "residuos al cuadrado, es menos sensible a unos pocos picos "
               "mal simulados que el RSR, por lo que ambos indicadores se "
               "recomiendan en conjunto: si RSR es alto pero MAE/STD(Oi) es "
               "bajo, el problema probablemente esté concentrado en pocos "
               "eventos extremos más que en el comportamiento general del "
               "modelo.",
        pasos=[
            "Se calcula el MAE del modelo (ver ficha de MAE): "
            "(1/n)·Σ|Pi−Oi|.",
            "Se calcula la desviación estándar de la serie observada "
            "respecto de su propio promedio: σO = √[(1/n)·Σ(Oi−μO)^2] "
            "(el mismo σO usado en el RSR).",
            "Se divide el MAE entre σO: MAE/STD(Oi) = MAE/σO.",
            "Se compara contra el umbral de Singh et al. (2004): una razón "
            "≤ 0.5 se considera un error de magnitud satisfactoria.",
        ]),
    "SEE (Auscultación de presas)": dict(
        formula="SEE = √[ Σ(Oi−Pi)^2 / (n−k−1) ]",
        como_leerlo="Error estándar de estimación, en las mismas unidades "
                     "que la variable medida (p. ej. mm de desplazamiento, "
                     "m de nivel piezométrico). Se usa para definir bandas "
                     "de comportamiento esperado alrededor de la predicción "
                     "del modelo (típicamente ±2·SEE): lecturas dentro de "
                     "esa banda se consideran parte del comportamiento "
                     "normal de la estructura; lecturas fuera de ±2·SEE (y "
                     "sobre todo fuera de ±3·SEE) son candidatas a revisión "
                     "como posibles anomalías de auscultación.",
        teoria="El SEE es el indicador central de los modelos de "
               "auscultación de presas de tipo HST (Hydrostatic-Season-"
               "Time) y similares, ampliamente usados para monitoreo de "
               "instrumentación geotécnica (piezómetros, extensómetros, "
               "péndulos, etc.). A diferencia de un modelo hidrológico, "
               "donde el objetivo es reproducir la serie observada lo mejor "
               "posible, en auscultación el modelo se ajusta a datos "
               "históricos \"de comportamiento normal\" y luego se usa para "
               "vigilar: cada nueva lectura se compara contra la predicción "
               "del modelo ± un múltiplo del SEE, y las lecturas que caen "
               "fuera de esa banda se marcan para inspección, ya que pueden "
               "indicar un cambio real de comportamiento de la presa (o del "
               "instrumento) y no solo ruido de medición. El parámetro k "
               "(número de variables/parámetros calibrados del modelo, por "
               "ejemplo los términos del polinomio HST) ajusta los grados "
               "de libertad (n−k−1) para no subestimar el error cuando el "
               "modelo tiene muchos parámetros ajustables; con k=0 el SEE "
               "es prácticamente equivalente a un RMSE corregido por "
               "muestra pequeña. (Salazar et al., 2017)",
        pasos=[
            "Se calculan los residuos del modelo, ei = Oi−Pi, para cada "
            "instante (aquí con el mismo signo que en RMSE/MAE).",
            "Se elige k: el número de parámetros/variables independientes "
            "calibrados en el modelo de auscultación (0 si no se está "
            "ajustando un modelo paramétrico, o el número de términos del "
            "polinomio/regresión usada).",
            "Se calculan los grados de libertad: n−k−1 (con mínimo 1 para "
            "evitar división por cero en series muy cortas).",
            "Se suman los residuos al cuadrado y se dividen entre los "
            "grados de libertad, y se toma la raíz: "
            "SEE = √[Σ(Oi−Pi)^2/(n−k−1)].",
            "Se cuentan cuántas lecturas caen dentro de ±2·SEE del valor "
            "predicho: ese porcentaje (ver ficha siguiente) es el criterio "
            "de \"comportamiento satisfactorio\" en auscultación, no un "
            "umbral fijo sobre el SEE mismo (que depende de las unidades y "
            "la escala de la variable medida).",
        ]),
    "% dentro de ±2·SEE": dict(
        formula="% dentro de ±2·SEE = 100 · (N° de |Oi−Pi| ≤ 2·SEE) / n",
        como_leerlo="Porcentaje de lecturas cuyo residuo cae dentro de la "
                     "banda de comportamiento esperado (±2·SEE alrededor de "
                     "la predicción del modelo). En un modelo de auscultación "
                     "bien calibrado y con residuos aproximadamente normales, "
                     "se espera que ~95% de las lecturas caigan dentro de "
                     "±2·SEE; un porcentaje bajo, o unas pocas lecturas muy "
                     "fuera de ±3·SEE, son las señales típicas usadas para "
                     "marcar posibles anomalías de instrumentación.",
        teoria="Este es el indicador de \"bondad de ajuste\" que realmente "
               "se usa en la práctica de auscultación de presas junto con el "
               "SEE (Salazar et al., 2017): el SEE por sí solo no tiene un "
               "umbral universal (depende de las unidades de la variable), "
               "pero el porcentaje de lecturas dentro de ±2·SEE sí es "
               "comparable entre instrumentos y presas, porque aprovecha que "
               "para residuos aproximadamente normales, ±2·SEE debería "
               "contener cerca del 95% de las observaciones y ±3·SEE cerca "
               "del 99.7%. Un porcentaje bajo indica que el modelo no está "
               "capturando bien el comportamiento normal de la estructura "
               "(hay que revisar la calibración), mientras que un porcentaje "
               "adecuado con algunas lecturas puntuales fuera de banda es "
               "justamente el patrón esperado para detectar anomalías reales.",
        pasos=[
            "Se calcula el SEE del modelo (ver ficha anterior) y sus "
            "residuos ei = Oi−Pi.",
            "Para cada lectura se verifica si |ei| ≤ 2·SEE (dentro de la "
            "banda de comportamiento esperado) o no.",
            "Se cuenta cuántas lecturas cumplen esa condición y se divide "
            "entre el total n, expresado en porcentaje.",
            "Un valor cercano a 95% (o mayor) se considera satisfactorio; "
            "valores bajos, o varias lecturas más allá de ±3·SEE, sugieren "
            "revisar la calibración del modelo o inspeccionar el "
            "instrumento/la estructura.",
        ]),
}


# -----------------------------------------------------------------------
# Escala de interpretación de cada indicador (para el "medidor" gráfico
# didáctico): bandas Malo/Regular/Bueno, consistentes con los umbrales
# usados en `theme.kpi_color_for` para el resaltado de color de la tabla.
# "gauge_type":
#   "higher_better" -> valor por debajo de t_regular es Malo, entre
#       t_regular y t_bueno es Regular, por encima de t_bueno es Bueno.
#   "symmetric_bias" -> se evalúa |valor| (en %, multiplicando por 100 si
#       as_pct=True porque el indicador es una fracción): <=t_bueno Bueno,
#       <=t_regular Regular, más allá Malo. El óptimo está en 0.
#   "open_error" -> no tiene un rango universal fijo (depende de las
#       unidades/magnitud del caudal); se compara relativamente entre las
#       corridas analizadas en vez de con umbrales fijos.
#   "lower_better" -> el óptimo es 0 y no puede ser negativo: valor <=
#       t_bueno es Bueno, <=t_regular es Regular, más allá es Malo
#       (opuesto de "higher_better").
# -----------------------------------------------------------------------
INDICATOR_SCALE = {
    # Errores en unidades de la variable: sin rango universal.
    "MAE": dict(gauge_type="open_error"),
    "STD": dict(gauge_type="open_error"),
    "RMSE": dict(gauge_type="open_error"),
    "SEE (Auscultación de presas)": dict(gauge_type="open_error"),
    # Único indicador con rangos de clasificación por defecto (Nash-Sutcliffe).
    "EF": dict(gauge_type="higher_better", t_regular=0.5, t_bueno=0.75,
               axis_lo=-1.0, axis_hi=1.0),
    # Los demás NO traen rangos Bueno/Regular/Malo (no se fuerzan): se
    # muestran con su valor, su óptimo y su rango teórico.
    "CD": dict(gauge_type="open_error", neutral=True),
    "R": dict(gauge_type="open_error", neutral=True),
    "Model Skill (Willmott)": dict(gauge_type="open_error", neutral=True),
    "CR1 (Sesgo del modelo)": dict(gauge_type="open_error", neutral=True),
    "CR4 (NS logarítmico)": dict(gauge_type="open_error", neutral=True),
    "CR5 (NS adaptado)": dict(gauge_type="open_error", neutral=True),
    "PBIAS (%)": dict(gauge_type="open_error", neutral=True),
    "KGE": dict(gauge_type="open_error", neutral=True),
    "RSR": dict(gauge_type="open_error", neutral=True),
    "MAE/STD(Oi)": dict(gauge_type="open_error", neutral=True),
    "% dentro de ±2·SEE": dict(gauge_type="open_error", neutral=True),
}


# -----------------------------------------------------------------------
# Calificación (Bueno/Regular/Malo) y descripción en texto de la escala
# de cada indicador, a partir de `INDICATOR_SCALE` (fuente única de los
# umbrales, para que la interfaz, el medidor gráfico y los reportes
# PDF/Word/Excel usen siempre el mismo criterio).
# -----------------------------------------------------------------------
QUALITY_COLORS = {"Bueno": "#1E9E6B", "Regular": "#D8A02A", "Malo": "#DD5353"}


def quality_label(indicator: str, value) -> str | None:
    """Devuelve "Bueno" / "Regular" / "Malo" según los umbrales de
    `INDICATOR_SCALE`, o None si el indicador no tiene un rango
    universal fijo (p. ej. MAE/STD/RMSE, "open_error") o el valor no es
    numérico."""
    scale = INDICATOR_SCALE.get(indicator)
    if not scale:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    gauge_type = scale.get("gauge_type")
    if gauge_type == "higher_better":
        if v >= scale["t_bueno"]:
            return "Bueno"
        if v >= scale["t_regular"]:
            return "Regular"
        return "Malo"
    if gauge_type == "symmetric_bias":
        av = abs(v) * 100.0 if scale.get("as_pct") else abs(v)
        if av <= scale["t_bueno"]:
            return "Bueno"
        if av <= scale["t_regular"]:
            return "Regular"
        return "Malo"
    if gauge_type == "lower_better":
        if v <= scale["t_bueno"]:
            return "Bueno"
        if v <= scale["t_regular"]:
            return "Regular"
        return "Malo"
    return None


def scale_description(indicator: str) -> str:
    """Texto plano describiendo los rangos Bueno/Regular/Malo de un
    indicador, para mostrar la escala de interpretación en la interfaz
    y en los reportes exportados."""
    scale = INDICATOR_SCALE.get(indicator, {})
    gauge_type = scale.get("gauge_type")
    if gauge_type == "higher_better":
        best = CRITERIA_REFERENCE.get(indicator, {}).get("best", 1)
        return (f"Bueno: valor >= {scale['t_bueno']:g} · Regular: entre "
                f"{scale['t_regular']:g} y {scale['t_bueno']:g} · Malo: valor < "
                f"{scale['t_regular']:g}. El óptimo es {best:g}.")
    if gauge_type == "symmetric_bias":
        return (f"Bueno: |valor| <= {scale['t_bueno']:g}% · Regular: entre "
                f"{scale['t_bueno']:g}% y {scale['t_regular']:g}% · Malo: por encima de "
                f"{scale['t_regular']:g}%. El óptimo es 0.")
    if gauge_type == "lower_better":
        return (f"Bueno: valor <= {scale['t_bueno']:g} · Regular: entre "
                f"{scale['t_bueno']:g} y {scale['t_regular']:g} · Malo: valor > "
                f"{scale['t_regular']:g}. El óptimo es 0 (no puede ser negativo).")
    if scale.get("neutral"):
        best = CRITERIA_REFERENCE.get(indicator, {}).get("best")
        opt = f" Valor de referencia (óptimo): {best:g}." if isinstance(best, (int, float)) else ""
        return ("Sin rango definido: este método no trae rangos de clasificación en la "
                "planilla original CT_2010; se interpreta comparando con el valor de "
                "referencia y entre corridas." + opt)
    return ("No tiene un rango universal fijo (depende de las unidades y la magnitud "
            "de la variable comparada): se interpreta comparando esta corrida contra "
            "las demás analizadas en el mismo estudio — un valor más bajo es mejor.")


def _range_text(indicator: str) -> str:
    """Texto compacto "mín a máx (óptimo: ...)" a partir de
    `CRITERIA_REFERENCE`, para la tabla resumen de métodos (ver
    `methods_summary_table`)."""
    crit = CRITERIA_REFERENCE.get(indicator)
    if not crit:
        return "—"
    if not crit.get("sheet"):
        return "Sin rango (interpretación)"

    def _fmt(v):
        if v in ("+", "+inf"):
            return "+∞"
        if v in ("-", "-inf"):
            return "-∞"
        try:
            return f"{float(v):g}"
        except (TypeError, ValueError):
            return str(v)

    return f"{_fmt(crit['min'])} a {_fmt(crit['max'])} (óptimo: {_fmt(crit['best'])})"


def methods_summary_table(selected_indicators: list[str]) -> pd.DataFrame:
    """Tabla resumen (DataFrame) de los métodos estadísticos de validación
    usados en esta corrida: una fila por indicador seleccionado, con qué
    mide, su fórmula, su rango/valor óptimo y la referencia bibliográfica.
    Pensada para mostrarse como tabla representativa, estética y
    exportable a PNG (ver `ct_tool.plots.styled_table_figure`), y para
    incluirse en el reporte igual que un gráfico más -- pedido explícito
    de la usuaria ("una tabla resumen de los métodos estadísticos que se
    usaron")."""
    rows = []
    for key in selected_indicators:
        crit = CRITERIA_REFERENCE.get(key)
        help_entry = INDICATOR_HELP.get(key)
        if not crit and not help_entry:
            continue
        rows.append({
            "Indicador": key,
            "Qué mide": (crit or {}).get("desc", ""),
            "Fórmula": (help_entry or {}).get("formula", ""),
            "Rango / Óptimo": _range_text(key),
            "Referencia": (crit or {}).get("ref", ""),
        })
    return pd.DataFrame(rows, columns=["Indicador", "Qué mide", "Fórmula", "Rango / Óptimo", "Referencia"])


# -----------------------------------------------------------------------
# Ranking compuesto: combina varios indicadores en un solo puntaje 0-1
# (1 = mejor) por corrida, para responder de forma más robusta "¿cuál
# serie se ajusta mejor?" sin depender de un único indicador (p. ej. EF
# puede estar dominado por un par de picos de crecida).
# -----------------------------------------------------------------------
def _score_bounded_by_one(v: float) -> float:
    """Para indicadores tipo EF/KGE/Model Skill/CR4/CR5: óptimo=1, pueden
    bajar mucho (hasta -inf); se recorta a [0,1] para el puntaje."""
    return float(np.clip(v, 0.0, 1.0))


def _score_correlation(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _score_cd(v: float) -> float:
    """CD: óptimo=1, puede ser mayor o menor a 1."""
    return float(np.clip(1.0 - abs(v - 1.0), 0.0, 1.0))


def _score_pbias(v: float) -> float:
    """PBIAS ya en %: se considera aceptable hasta ±25%, óptimo en 0%."""
    return float(np.clip(1.0 - abs(v) / 25.0, 0.0, 1.0))


def _score_cr1(v: float) -> float:
    """CR1 es una fracción (no %): se compara en la misma escala que PBIAS."""
    return float(np.clip(1.0 - abs(v) * 100.0 / 25.0, 0.0, 1.0))


# Nombre de columna (igual que en `goodness_of_fit`) -> función de puntaje.
INDICATOR_SCORERS = {
    "EF": _score_bounded_by_one,
    "KGE": _score_bounded_by_one,
    "Model Skill (Willmott)": _score_bounded_by_one,
    "CR4 (NS logarítmico)": _score_bounded_by_one,
    "CR5 (NS adaptado)": _score_bounded_by_one,
    "R": _score_correlation,
    "CD": _score_cd,
    "PBIAS (%)": _score_pbias,
    "CR1 (Sesgo del modelo)": _score_cr1,
}


def rank_runs(stats_table: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Arma un ranking de corridas simuladas combinando varios
    indicadores clave (ver `INDICATOR_SCORERS`) en un único "Puntaje
    compuesto" de 0 a 1 (1 = mejor ajuste posible), como referencia
    visual rápida de qué serie se ajusta mejor sin depender de un solo
    indicador.

    No reemplaza el criterio experto ni los indicadores individuales
    (por eso se muestran todos igual en la tabla): es un resumen
    didáctico adicional.

    Parameters
    ----------
    stats_table : salida de `compare_multiple_runs` (índice = nombre de
        la corrida, columnas = indicadores).

    Returns
    -------
    (ranking, indicadores_usados) : DataFrame ordenado de mejor a peor
        con una columna "Puntaje compuesto (0-1)" agregada, y la lista
        de nombres de indicadores efectivamente usados en el puntaje
        (los que estén presentes en `stats_table`).
    """
    used = [k for k in INDICATOR_SCORERS if k in stats_table.columns]
    if not used:
        raise ValueError(
            "La tabla de indicadores no tiene ninguna de las columnas "
            "usadas para el ranking compuesto (EF, R, KGE, CD, PBIAS...).")
    scores = pd.DataFrame(
        {k: stats_table[k].astype(float).apply(INDICATOR_SCORERS[k]) for k in used},
        index=stats_table.index)
    composite = scores.mean(axis=1)
    out = stats_table.copy()
    out["Puntaje compuesto (0-1)"] = composite
    out = out.sort_values("Puntaje compuesto (0-1)", ascending=False)
    return out, used


def goodness_of_fit_table(obs, sim, eps: float = EPS_DEFAULT) -> pd.DataFrame:
    """Igual que `goodness_of_fit` pero devuelve una tabla (DataFrame)
    lista para mostrar en la interfaz o exportar, incluyendo el rango
    de referencia y el valor óptimo de cada indicador."""
    values = goodness_of_fit(obs, sim, eps=eps)
    rows = []
    for key, val in values.items():
        ref = CRITERIA_REFERENCE.get(key, {})
        rows.append({
            "Indicador": key,
            "Valor": val,
            "Óptimo": ref.get("best", "-"),
            "Mín": ref.get("min", "-") if ref.get("sheet") else "-",
            "Máx": ref.get("max", "-") if ref.get("sheet") else "-",
            "Descripción": ref.get("desc", ""),
            "Referencia": ref.get("ref", ""),
        })
    return pd.DataFrame(rows)


def compare_multiple_runs(df: pd.DataFrame, obs_col: str, sim_cols: list[str],
                           eps: float = EPS_DEFAULT, k: int = 0) -> pd.DataFrame:
    """Calcula los indicadores para varias corridas simuladas a la vez
    (equivalente a comparar varias columnas de "Source" contra la
    columna observada), y arma una tabla resumen (una fila por
    corrida).

    `k` (grados de libertad consumidos por parámetros calibrados) se
    pasa tal cual a `goodness_of_fit` -- solo lo usa el SEE de
    auscultación de presas."""
    rows = []
    for col in sim_cols:
        vals = goodness_of_fit(df[obs_col], df[col], eps=eps, k=k)
        vals["Corrida"] = col
        rows.append(vals)
    out = pd.DataFrame(rows).set_index("Corrida")
    return out


# -----------------------------------------------------------------------
# Traza de cálculo: para mostrar, indicador por indicador, "con qué
# datos se trabajó, los cálculos intermedios y el resultado final" en
# vez de solo el valor final (pedido explícito de la usuaria). Se
# apoya en los valores intermedios que ya expone
# `goodness_of_fit_detailed` bajo "_detalle", evitando volver a
# calcular nada.
# -----------------------------------------------------------------------

# Para cada indicador: lista ordenada de (etiqueta, clave-en-detalle,
# tipo-de-formato). tipo-de-formato: "n" (entero), "g" (número general,
# hasta 6 cifras significativas) o "pct" (número + "%").
INDICATOR_TRACE_SPEC: dict[str, list[tuple[str, str, str]]] = {
    "MAE": [
        ("n (pares de datos válidos)", "n", "n"),
        ("Σ|Pi−Oi| (suma de residuos absolutos)", "sum_abs_resid", "g"),
    ],
    "STD": [
        ("n (pares de datos válidos)", "n", "n"),
    ],
    "RMSE": [
        ("n (pares de datos válidos)", "n", "n"),
        ("Σ(Pi−Oi)² (suma de residuos al cuadrado)", "ss_res", "g"),
    ],
    "EF": [
        ("Avg(Oi) = μO", "avg_o", "g"),
        ("Σ(Oi−μO)² (variabilidad observada)", "ss_o", "g"),
        ("Σ(Pi−Oi)² (error del modelo)", "ss_res", "g"),
    ],
    "CD": [
        ("Avg(Oi) = μO", "avg_o", "g"),
        ("Σ(Oi−μO)²", "ss_o", "g"),
        ("Σ(Pi−μO)²", "ss_p_from_o", "g"),
    ],
    "R": [
        ("Avg(Oi) = μO, Avg(Pi) = μP", "avg_o", "g"),
        ("Σ(Oi−μO)(Pi−μP) (covarianza)", "cov_op", "g"),
        ("Σ(Oi−μO)²", "ss_o", "g"),
        ("Σ(Pi−μP)²", "ss_p", "g"),
    ],
    "Model Skill (Willmott)": [
        ("Σ(Pi−Oi)² (error del modelo)", "ss_res", "g"),
        ("Σ(|Pi−μO|+|Oi−μO|)² (denominador de Willmott)", "willmott_denom", "g"),
    ],
    "CR1 (Sesgo del modelo)": [
        ("Avg(Oi) = μO", "avg_o", "g"),
        ("Avg(Pi) = μP", "avg_p", "g"),
    ],
    "CR4 (NS logarítmico)": [
        ("ln(μO+ε)", "ln_avg_o", "g"),
        ("Σ(ln Pi−ln Oi)²", "num_cr4", "g"),
        ("Σ(ln Oi−ln μO)²", "den_cr4", "g"),
    ],
    "CR5 (NS adaptado)": [
        ("Avg(Oi) = μO", "avg_o", "g"),
        ("Σ(Oi+μO)(Pi−Oi)² (numerador ponderado)", "num_cr5", "g"),
        ("Σ(Oi+μO)(Oi−μO)² (denominador ponderado)", "den_cr5", "g"),
    ],
    "PBIAS (%)": [
        ("Σ(Pi−Oi) (residuo acumulado)", "sum_resid", "g"),
        ("ΣOi (volumen observado total)", "sum_o", "g"),
    ],
    "KGE": [
        ("r (correlación de Pearson)", "r_pearson", "g"),
        ("β = μP/μO (sesgo de volumen)", "beta", "g"),
        ("γ (razón de coeficientes de variación)", "gamma", "g"),
    ],
    "RSR": [
        ("σO = √[Σ(Oi−μO)²/n] (desv. estándar observada)", "std_o", "g"),
        ("Σ(Pi−Oi)² (para el RMSE)", "ss_res", "g"),
    ],
    "MAE/STD(Oi)": [
        ("σO = √[Σ(Oi−μO)²/n] (desv. estándar observada)", "std_o", "g"),
        ("Σ|Pi−Oi| (para el MAE)", "sum_abs_resid", "g"),
    ],
    "SEE (Auscultación de presas)": [
        ("k (parámetros calibrados)", "k", "n"),
        ("Grados de libertad, n−k−1", "dof", "n"),
        ("Σ(Oi−Pi)² (suma de residuos al cuadrado)", "ss_res", "g"),
    ],
    "% dentro de ±2·SEE": [
        ("N° de lecturas dentro de ±2·SEE", "n_within_2see", "n"),
        ("N° de lecturas dentro de ±3·SEE", "n_within_3see", "n"),
        ("N° de lecturas más allá de ±3·SEE (posibles anomalías)", "n_anomalos", "n"),
    ],
}


def calculation_trace(indicator: str, detalle: dict, resultado) -> list[tuple[str, str]]:
    """Arma la traza de cálculo de un indicador ya calculado: una lista
    ordenada de (etiqueta, valor-formateado) que empieza con "los datos
    con que se trabajó" (n, y los parámetros relevantes), sigue con los
    cálculos intermedios propios de ESE indicador, y termina con el
    resultado final -- para mostrar el "paso del cálculo" en la
    interfaz y en el reporte, no solo el número final.

    `detalle` es el diccionario devuelto bajo "_detalle" por
    `goodness_of_fit_detailed`. `resultado` es el valor final del
    indicador (tal como aparece en la tabla de resultados)."""

    def _fmt(key: str, kind: str) -> str:
        val = detalle.get(key)
        if val is None:
            return "-"
        if kind == "n":
            return f"{int(val):,}".replace(",", " ")
        if kind == "pct":
            return f"{float(val):.2f}%"
        return f"{float(val):.6g}"

    rows: list[tuple[str, str]] = []
    rows.append(("n (datos usados)", _fmt("n", "n")))

    spec = INDICATOR_TRACE_SPEC.get(indicator, [])
    for label, key, kind in spec:
        if key == "n":  # ya se mostró arriba como "dato usado"
            continue
        rows.append((label, _fmt(key, kind)))

    try:
        resultado_fmt = f"{float(resultado):.6g}"
    except (TypeError, ValueError):
        resultado_fmt = str(resultado)
    rows.append((f"Resultado: {indicator}", resultado_fmt))
    return rows


# ---------------------------------------------------------------------------
# Análisis múltiple / en paralelo: varias variables (p. ej. caudal + varios
# piezómetros) analizadas de una sola vez, cada una comparando el mismo
# conjunto de "modelos" (M1, M2, M3...). Permite responder, en un solo
# vistazo, cómo se comporta cada modelo a través de TODAS las variables
# analizadas -- no solo dentro de una -- que es justo lo que muestran los
# gráficos de barras agrupadas "por variable y modelo" y el ranking
# promedio por modelo.
# ---------------------------------------------------------------------------

def pivot_indicator_by_variable(results: dict[str, pd.DataFrame], indicator: str) -> pd.DataFrame:
    """A partir de un diccionario {nombre_variable: tabla_de_indicadores}
    (cada tabla con índice = nombre de modelo, tal como devuelve
    `compare_multiple_runs` una vez renombrado el índice de columna
    simulada a nombre de modelo), arma una tabla pivote con índice =
    variable, columnas = modelo y valores = el indicador pedido (p.
    ej. "EF", "KGE", "PBIAS (%)"). Es la forma que necesitan los
    gráficos de barras agrupadas "por variable y modelo"."""
    rows = {}
    for var_name, table in results.items():
        if table is not None and indicator in table.columns:
            rows[var_name] = table[indicator].astype(float)
    if not rows:
        raise ValueError(f"Ninguna variable tiene calculado el indicador \"{indicator}\".")
    return pd.DataFrame(rows).T  # índice=variable, columnas=modelo


def average_ranking_by_model(results: dict[str, pd.DataFrame]
                              ) -> tuple[pd.DataFrame, list[str]]:
    """Calcula el ranking compuesto (`rank_runs`) por separado para
    cada variable analizada, y promedia el puntaje de cada modelo a
    través de todas las variables donde ese modelo tenga resultado --
    responde al pedido de "un ranking promedio por modelo, para ver
    los resultados de toda la parte de validación" (todas las
    variables juntas, no una por una).

    Returns
    -------
    (ranking, indicadores_usados) : DataFrame con índice = modelo,
        columnas "Puntaje promedio (0-1)" (ordenado de mejor a peor) y
        "N° de variables" (cuántas variables entraron en el promedio
        de ese modelo -- por si algún modelo no tiene columna asignada
        en todas), y la lista de indicadores usados para el puntaje
        compuesto de cada variable (la misma que devuelve `rank_runs`).
    """
    per_variable_scores = {}
    used_ref: list[str] = []
    for var_name, table in results.items():
        try:
            ranked, used = rank_runs(table)
        except Exception:
            continue
        per_variable_scores[var_name] = ranked["Puntaje compuesto (0-1)"]
        if not used_ref:
            used_ref = used
    if not per_variable_scores:
        raise ValueError("No se pudo calcular el ranking compuesto en ninguna variable "
                          "(revise que cada variable tenga al menos 2 modelos comparables).")
    combined = pd.DataFrame(per_variable_scores)  # índice=modelo, columnas=variable
    out = pd.DataFrame({
        "Puntaje promedio (0-1)": combined.mean(axis=1),
        "N° de variables": combined.notna().sum(axis=1).astype(int),
    })
    out = out.sort_values("Puntaje promedio (0-1)", ascending=False)
    return out, used_ref
