FROM python:3.12-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

# Install PyTorch CPU-only first (saves ~1.2GB vs full CUDA version)
RUN pip3 install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip3 install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

# Create directory for model cache (will be mounted as volume)
RUN mkdir -p /root/.cache/huggingface

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1


CMD ["fastapi", "run", "app/main.py", "--port", "8000"]