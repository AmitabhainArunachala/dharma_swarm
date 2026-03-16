FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements-ginko.txt .
RUN pip install --no-cache-dir -r requirements-ginko.txt

# Copy source
COPY dharma_swarm/ /app/dharma_swarm/
COPY setup.py pyproject.toml README.md ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir .

# Create data directories
RUN mkdir -p /root/.dharma/ginko/agents \
    /root/.dharma/ginko/data \
    /root/.dharma/ginko/signals \
    /root/.dharma/ginko/regime \
    /root/.dharma/ginko/reports \
    /root/.dharma/ginko/sec

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/fleet || exit 1

CMD ["uvicorn", "dharma_swarm.swarmlens_app:app", "--host", "0.0.0.0", "--port", "8080"]
