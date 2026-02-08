FROM python:3.12-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

# Install PyTorch CPU-only first (saves ~1.2GB vs full CUDA version)
RUN pip3 install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip3 install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

CMD ["uvicorn", "run", "app/main.py",  "--host", "0.0.0.0", "--port", "5002"]
