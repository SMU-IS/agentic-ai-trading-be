# test_preprocess_single_post.py
import json
import redis
from app.scripts.storage import RedisStreamStorage
from app.scripts.checkpoint import RedisCheckpoint
from app.services._01_preprocesser import PreprocessingService
from app.services._02_ticker_identification import TickerIdentificationService
from app.services._03_event_identification import EventIdentifierService
from app.scripts.aws_bucket_access import AWSBucket
from app.core.config import env_config

# Setup Redis and S3
redis_client = redis.Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True
)
bucket = AWSBucket()

# method to view what is currently in the stream
# to change last_id to dynamic - currently still testing hence start from 0-0
def view_stream(stream, count=50):
    entries = stream.read(last_id="0-0", count=count, block_ms=1000)
    if not entries:
        print(f"{stream.stream_name} is empty\n")
        return entries
    for _, messages in entries:
        for msg_id, data in messages:
            print(f"Post {msg_id}:")
            print(json.dumps(data, indent=2))
            print("\n---\n")
    return entries


# Setup streams & services
reddit_stream = RedisStreamStorage("reddit_stream", redis_client)
# preproc stream to be consumed by ticker service
preprocessing_stream = RedisStreamStorage("preproc_stream", redis_client)
# ticker stream to be consumed by event service
ticker_stream = RedisStreamStorage("ticker_stream", redis_client)
# event stream to be consumed by credibility service
event_stream = RedisStreamStorage("event_stream", redis_client)
# all tickers set to be updated and sent to scraping service
all_tickers = set()

# keys for AWS bucket files
CLEANED_KEY = "data/processed/cleaned_tickers.json"
ALIAS_KEY = "data/processed/alias_to_canonical.json"
EVENTS_KEY = "data/config/financial_event_types.json"

# load files from AWS bucket
cleaned_tickers = json.loads(bucket.read_text(CLEANED_KEY))
alias_to_canonical = json.loads(bucket.read_text(ALIAS_KEY))
events_types = json.loads(bucket.read_text(EVENTS_KEY))

# Service Initialisation
# todo: to update checkpoint and read based on checkpoint
# currently 0-0 to test first 50
# checkpoint = RedisCheckpoint("preprocess")
# checkpoint = RedisCheckpoint("tickeridentification")
# checkpoint = RedisCheckpoint("eventidentification")

preprocessor = PreprocessingService()
eventidentifier = EventIdentifierService(event_list=events_types)
ticker_service = TickerIdentificationService(
    cleaned_tickers=cleaned_tickers,
    alias_to_canonical=alias_to_canonical,
)

# # Clear streams for testing
preprocessing_stream.clear_stream()
ticker_stream.clear_stream()
event_stream.clear_stream()

# Consume from Reddit stream
entries = reddit_stream.read(last_id="0-0", count=50, block_ms=5000)

for _, messages in entries:
    for msg_id, data in messages:
        post_content = data.get("data", data)
        processed = preprocessor.preprocess_post(post_content)
        preprocessing_stream.save(processed)
        # checkpoint.save(msg_id)



# Extract tickers 
preproc_entries = preprocessing_stream.read(last_id="0-0", count=50, block_ms=5000)
try:
    for _, messages in preproc_entries:
        for msg_id, data in messages:
            post_content = data.get("data", data)
            tickers_post = ticker_service.process_post(post_content)
            if not tickers_post:
                continue

            ticker_stream.save(tickers_post)

            ticker_metadata = tickers_post.get("ticker_metadata", {})
            if not ticker_metadata:
                continue

            simple_ticker_metadata = {
                ticker: info["OfficialName"]
                for ticker, info in ticker_metadata.items()
            }

            redis_client.hset(
                "ticker_to_official_name",
                mapping=simple_ticker_metadata
            )

            all_tickers.update(simple_ticker_metadata.keys())

            # Intermediate S3 save (save at every new 100 aliases)
            if (
                ticker_service.new_alias_count > 0
                and ticker_service.new_alias_count % 100 == 0
            ):
                print(
                    f"[S3 Save] {ticker_service.new_alias_count} new aliases added "
                    f"(intermediate save)"
                )
                bucket.write_text(
                    json.dumps(ticker_service.alias_to_canonical, indent=2),
                    ALIAS_KEY,
                )

except Exception as e:
    print(f"[Error] Processing crashed: {e}")

finally:
    if ticker_service.new_alias_count > 0:
        print(
            f"[S3 Save] Final save — {ticker_service.new_alias_count} new aliases added"
        )
        bucket.write_text(
            json.dumps(ticker_service.alias_to_canonical, indent=2),
            ALIAS_KEY,
        )

# Add newly identified tickers to be consumed at scraping service
if all_tickers:
    redis_client.sadd("all_identified_tickers", *all_tickers)

# Event Identification
ticker_entries = ticker_stream.read(last_id="0-0", count=50, block_ms=5000)
for _, messages in ticker_entries:
    for msg_id, data in messages:
        post_content = data.get("data", data)
        event_data = eventidentifier.analyse_event(post_content)
        event_stream.save(event_data)
        print(msg_id)
        # checkpoint.save(msg_id)

# View output
print("\n=== Content in ticker stream ===\n")
view_stream(ticker_stream)

print("\n=== Current tickers in Redis ===\n")
for ticker, name in redis_client.hgetall("ticker_to_official_name").items():
    print(f"{ticker}: {name}")

print("\n=== All tickers set in Redis ===\n")
for ticker in redis_client.smembers("all_identified_tickers"):
    print(ticker)

print("\n=== Content in event stream ===\n")
view_stream(event_stream)