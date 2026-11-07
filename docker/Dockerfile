# WIC 2026 Trading Agent - Docker Configuration

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libibapi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libibapi \
    && rm -rf /var/lib/apt/lists/*

# Copy from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application
COPY src ./src
COPY pyproject.toml .

# Create non-root user
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app
USER trader

# Environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import src.config.settings; print('OK')" || exit 1

# Default command
CMD ["python", "-m", "src.main", "run"]