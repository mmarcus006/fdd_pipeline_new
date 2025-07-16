# FDD Pipeline Docker Image
# Multi-stage build for production deployment

# Stage 1: Base Python image with system dependencies
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Required for building Python packages
    build-essential \
    # Required for Playwright
    wget \
    gnupg \
    # Required for MinerU/PDF processing
    poppler-utils \
    tesseract-ocr \
    # Required for PostgreSQL client
    libpq-dev \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN pip install uv

# Set working directory
WORKDIR /app

# Stage 2: Dependencies
FROM base as dependencies

# Copy dependency files
COPY pyproject.toml .
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN uv venv
RUN . .venv/bin/activate && uv pip install -r requirements.txt

# Install Playwright browsers
RUN . .venv/bin/activate && playwright install chromium

# Stage 3: Application
FROM base as application

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application code
COPY . /app

# Install the application in editable mode
RUN . .venv/bin/activate && uv pip install -e .

# Create non-root user
RUN useradd -m -u 1000 fdduser && chown -R fdduser:fdduser /app
USER fdduser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1

# Expose ports
EXPOSE 8000 4200

# Default command (can be overridden)
CMD ["python", "-m", "src.api.run", "--host", "0.0.0.0", "--port", "8000"]