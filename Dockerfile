FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; add build-essential only if a dependency needs
# to compile from source in your environment.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 3978

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3978"]
