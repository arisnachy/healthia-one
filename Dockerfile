FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY pyproject.toml constraints-release.txt README.md LICENSE ./
COPY app ./app
COPY healthia_one ./healthia_one
COPY healthia_agent ./healthia_agent
COPY web ./web
COPY demo ./demo
RUN pip install --no-cache-dir -c constraints-release.txt .

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
