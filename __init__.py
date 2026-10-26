"""
CT_2010 - Herramienta de Comparación (Comparison Tool)
=======================================================

Reimplementación en Python de la planilla Excel/VBA "CT_2010.xlsm"
(Mauricio Villazon, basada en hojas de Raul Vázquez, Patrick Willems,
Ahmed Abuelnasr, Bernard Biesbrouck -K.U.Leuven- y prof. Bauwens -VUB-)
utilizada para evaluar el desempeño de modelos hidrológicos
(observado vs. simulado) mediante:

  * Indicadores estadísticos de bondad de ajuste (MAE, STD, RMSE, EF,
    CD, R, Model Skill, CR1, CR4, CR5).
  * Análisis de valores extremos (POT - Peaks Over Threshold) de
    caudales máximos y mínimos, con transformación Box-Cox y
    periodo de retorno.
  * Gráficos de diagnóstico (hidrograma, bisectriz, curva de
    duración, residuos, valores extremos).

Este paquete es independiente de Excel/VBA: solo requiere Python y
las librerías científicas estándar (numpy, pandas, scipy,
matplotlib).
"""

__version__ = "1.0.0"
