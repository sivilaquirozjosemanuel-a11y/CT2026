FROM python:3.12-slim

# Tipografías equivalentes a Arial / Times New Roman / Calibri / Cambria para los gráficos y el PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces ejecuta el contenedor con un usuario no-root (uid 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH MPLBACKEND=Agg PORT=7860
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
EXPOSE 7860
CMD ["python", "main.py"]
