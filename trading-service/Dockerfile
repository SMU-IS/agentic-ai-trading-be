FROM python:3.11-slim

WORKDIR /code

# Install dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy app code
COPY . .

# Expose FastAPI port
EXPOSE 9000

# Default envs (optional)
ENV PYTHONUNBUFFERED=1

# Start FastAPI with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]