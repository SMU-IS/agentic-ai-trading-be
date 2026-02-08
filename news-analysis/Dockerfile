FROM python:3.12-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r /code/requirements.txt

# Pre-download FinBERT model to avoid delays on first request
# RUN python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
#     AutoTokenizer.from_pretrained('ProsusAI/finbert'); \
#     AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert')"

COPY ./app /code/app

CMD ["fastapi", "run", "app/main.py",  "--host", "0.0.0.0", "--port", "5002"]
