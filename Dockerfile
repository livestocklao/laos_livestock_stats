# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build stage - for installing dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Set build environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Production stage - minimal runtime image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Set runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    PORT=8050 \
    PYTHONPATH=/app \
    PATH="/root/.local/bin:${PATH}"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Create application directories
RUN mkdir -p /app/data /app/assets /app/logs /app/utils /app/views \
    && chown -R appuser:appuser /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Ensure proper permissions
RUN chmod -R 755 /app \
    && chown -R appuser:appuser /app/data /app/logs

# Switch to non-root user
USER appuser

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose application port
EXPOSE ${PORT}

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "═══════════════════════════════════════════"\n\
echo "  Livestock Disease Monitoring System"\n\
echo "  Environment: ${ENVIRONMENT:-production}"\n\
echo "  Port: ${PORT:-8050}"\n\
echo "═══════════════════════════════════════════"\n\
\n\
# Verify data directory exists\n\
if [ ! -d "/app/data" ]; then\n\
    echo "⚠️  Creating data directory..."\n\
    mkdir -p /app/data\n\
fi\n\
\n\
# Check for development mode\n\
if [ "${ENVIRONMENT}" = "development" ]; then\n\
    echo "🔧 Running in DEVELOPMENT mode"\n\
    if [ ! -f "/app/data/db.xlsx" ]; then\n\
        echo "⚠️  Warning: data/db.xlsx not found"\n\
        echo "   Place your Excel file at data/db.xlsx"\n\
    fi\n\
fi\n\
\n\
# Check for Google credentials in production\n\
if [ "${ENVIRONMENT}" != "development" ]; then\n\
    echo "☁️  Running in PRODUCTION mode"\n\
    if [ -z "${GOOGLE_CREDENTIALS_JSON}" ] && [ ! -f "/app/assets/credentials.json" ]; then\n\
        echo "⚠️  Warning: Google credentials not found"\n\
        echo "   Set GOOGLE_CREDENTIALS_JSON environment variable"\n\
        echo "   Or mount credentials.json at /app/assets/credentials.json"\n\
    fi\n\
    \n\
    if [ -z "${ADMIN_USERNAME}" ] || [ -z "${ADMIN_PASSWORD}" ]; then\n\
        echo "⚠️  Warning: Admin credentials not set"\n\
        echo "   Set ADMIN_USERNAME and ADMIN_PASSWORD environment variables"\n\
    fi\n\
fi\n\
\n\
echo "🚀 Starting application..."\n\
exec python app.py\n\
' > /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command
CMD ["python", "app.py"]