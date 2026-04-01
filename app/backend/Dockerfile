FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy dependency definitions first for better Docker layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# Copy application code
COPY src ./src
COPY scripts/start.sh ./

EXPOSE 8000

CMD ["./start.sh"]
