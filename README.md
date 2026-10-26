---
title: CT 2010 Web
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# CT · Comparación de Modelos — versión web

Versión web (NiceGUI) de la herramienta CT_2010. Usa **exactamente el mismo código de cálculo** que
la versión de escritorio (`ct_tool/`): indicadores de validación, extremos (POT / Box-Cox), gráficos y
reportes PDF / Word / Excel. Metodología original: PhD. Mauricio Villazón — K.U.Leuven / UMSS.

## Flujo
1. **Datos:** suba un CSV/Excel (o cargue el caso de ejemplo), elija *Eje X*, *Observado* y *Simulado(s)*.
   La tabla es editable (+ Fila, + Columna).
2. **▶ Ejecutar análisis:** pregunta qué métodos usar y genera solo esas pestañas. Si el Eje X es una
   fecha, los extremos y sus 14 gráficos se generan solos.
3. **Validación:** una pestaña por método (teoría, fórmula, pasos, escala, cálculo con tus datos).
4. **Reporte:** tabla final de indicadores (exportable a PNG), ranking, tabla resumen de métodos y
   exportación a PDF / Word / Excel (varios formatos → un .zip).

Arriba a la derecha: tamaño del texto, letra de los gráficos y modo claro/oscuro (se recuerdan).

## Ejecutar en local
```bash
pip install -r requirements.txt
python main.py          # abre http://localhost:7860
```

## Publicar en Hugging Face Spaces (Docker)
1. Cree un Space nuevo → SDK **Docker** (puede ser *Private*).
2. Suba el contenido de esta carpeta (incluido este `README.md`, que ya trae la cabecera necesaria).
3. El Space construye la imagen y queda en `https://huggingface.co/spaces/<usuario>/<nombre>`.
4. Opcional: en *Settings → Variables and secrets* defina `CT_STORAGE_SECRET` con una cadena aleatoria.

También sirve en Render, Railway, Fly.io o cualquier servidor con Docker:
`docker build -t ct-web . && docker run -p 7860:7860 ct-web`.

## Privacidad
Los archivos subidos se leen en memoria/temporal y no se guardan; las imágenes de cada sesión se
borran al cerrar la pestaña. **Esta versión no tiene contraseña**: antes de abrirla a más personas
conviene dejar el Space privado o agregar una clave.

## Paridad con la versión de escritorio
La versión web incluye lo mismo que el escritorio:
- **Análisis múltiple** (varias variables × varios modelos): EF/KGE, PBIAS, ranking promedio, dispersión y series; entra al reporte exportado.
- **Guardar / abrir proyectos** `.ctproj` (compatibles con el escritorio).
- **Estilo del reporte** (letra, alineación, tablas) y **colores y líneas por corrida/modelo**.
- **Pegar datos** desde Excel/texto, tabla vacía y edición celda por celda.
- Selector de letra de gráficos, tamaño de texto, modo oscuro, tabla final de indicadores.

Pendiente: contraseña de acceso (se agrega cuando se defina).
