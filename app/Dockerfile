# Dockerfile for the Flask recommender app
# Multi-stage build: builder -> runtime

FROM python:3.10-slim AS builder

# Prevent Python from buffering stdout/stderr (helps with logs)
ENV PYTHONUNBUFFERED=1

WORKDIR /wheels

# Install packages needed to build wheels (kept minimal)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libssl-dev libffi-dev python3-dev cargo git \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements and build wheels into /wheels to cache builds
COPY requirements.txt /wheels/requirements.txt

# Upgrade pip tools and build wheels for all requirements
RUN pip install --upgrade pip setuptools wheel \
    && pip wheel --wheel-dir=/wheels -r /wheels/requirements.txt || true


FROM python:3.10-slim AS runtime

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Create a non-root user to run the app with a home directory
RUN groupadd -r app && useradd -r -g app -m -d /home/app app || true

# Copy built wheels from builder (if any) and requirements
COPY --from=builder /wheels /wheels
COPY requirements.txt /app/requirements.txt

# Install dependencies: prefer wheels produced in the builder stage if present
RUN if [ -d /wheels ] && [ "$(ls -A /wheels)" ]; then \
      pip install --no-cache-dir --upgrade pip && \
      pip install --no-index --find-links=/wheels -r /app/requirements.txt ; \
    else \
      pip install --no-cache-dir -r /app/requirements.txt ; \
    fi

# Copy application code
COPY . /app/

# Create telemetry directory and give ownership to app user
RUN mkdir -p /var/log/recsys && chown -R app:app /app /var/log/recsys
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RUN mkdir -p /tmp/prometheus && chmod 777 /tmp/prometheus
USER app

# Expose the port used by the Flask app
EXPOSE 8082

# Default command runs the Flask app file shipped in app/
CMD ["python", "app_flask.py"]
