FROM python:3.11-slim

WORKDIR /code

# Install Poetry or pip dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy source code
COPY ./src /code/src

# Create non-root user
CMD ["python", "-m", "src.main"]
