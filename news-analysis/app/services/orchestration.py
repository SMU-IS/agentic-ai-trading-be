import json
from datetime import datetime, timezone

import redis

from app.core.config import env_config
from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.scripts.aws_bucket_access import AWSBucket
from app.scripts.checkpoint import RedisCheckpoint
from app.scripts.storage import RedisStreamStorage
from app.services import (
    EventIdentifierService,
    PreprocessingService,
    TickerIdentificationService,
    VectorisationService,
)

# Setup Redis and S3
redis_client = redis.Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True,
)

bucket = AWSBucket()

# Setup streams & services
reddit_stream = RedisStreamStorage(env_config.redis_reddit_stream, redis_client)
# # preproc stream to be consumed by ticker service
preprocessing_stream = RedisStreamStorage(env_config.redis_preproc_stream, redis_client)
# # ticker stream to be consumed by event service
ticker_stream = RedisStreamStorage(env_config.redis_ticker_stream, redis_client)
# event stream to be consumed by credibility service
event_stream = RedisStreamStorage(env_config.redis_event_stream, redis_client)
# # ticker stream to be consumed by event service
sentiment_stream = RedisStreamStorage(env_config.redis_sentiment_stream, redis_client)
# event stream to be consumed by credibility service
credibility_stream = RedisStreamStorage(
    env_config.redis_credibility_stream, redis_client
)


# all tickers set to be updated and sent to scraping service
all_tickers = set()
removed_posts = []


# load files from AWS bucket
cleaned_tickers = json.loads(bucket.read_text(env_config.aws_bucket_cleaned_key))
alias_to_canonical = json.loads(bucket.read_text(env_config.aws_bucket_alias_key))
events_types = json.loads(bucket.read_text(env_config.aws_bucket_events_key))


async def run_pipeline():
    # Service Initialisation
    preproc_checkpoint = RedisCheckpoint("preprocess", redis_client)
    ticker_checkpoint = RedisCheckpoint("tickeridentification", redis_client)
    event_checkpoint = RedisCheckpoint("eventidentification", redis_client)
    sentiment_checkpoint = RedisCheckpoint("sentiment", redis_client)
    credibility_checkpoint = RedisCheckpoint("credibility", redis_client)
    vectorisation_checkpoint = RedisCheckpoint("vectorisation", redis_client)

    # Service Initialisation
    preprocessor = PreprocessingService()

    eventidentifier = EventIdentifierService(event_list=events_types)
    ticker_service = TickerIdentificationService(
        cleaned_tickers=cleaned_tickers,
        alias_to_canonical=alias_to_canonical,
    )

    # TODO: Intialiase credibility service - jiayen
    # TODO: Intialiase sentiment service - jiayen
    vectorisation_service = VectorisationService()

    # # Clear streams for testing
    # preprocessing_stream.clear_stream()
    # ticker_stream.clear_stream()
    # event_stream.clear_stream()

    try:
        while True:
            # Step 1: Consume scrapped data from Reddit stream
            preproc_last_id = preproc_checkpoint.load()
            reddit_entries = reddit_stream.read(
                last_id=preproc_last_id, count=10, block_ms=5000
            )
            if not reddit_entries:
                continue
            for _, messages in reddit_entries:
                for msg_id, data in messages:
                    post_content = data.get("data", data)
                    processed = preprocessor.preprocess_post(post_content)
                    preprocessing_stream.save(processed)
                    preproc_checkpoint.save(msg_id)
            print("preprocessing done\n\n\n")

            # Step 2: Extract tickers
            ticker_last_id = ticker_checkpoint.load()
            preproc_entries = preprocessing_stream.read(
                last_id=ticker_last_id, count=10, block_ms=5000
            )
            if not preproc_entries:
                continue
            for _, messages in preproc_entries:
                for msg_id, data in messages:
                    tickers_post = ticker_service.process_post(data)
                    if not tickers_post:
                        continue
                    ticker_metadata = tickers_post.get("ticker_metadata", {})
                    if not ticker_metadata:
                        tickers_post["removed_reason"] = "No ticker identified"
                        tickers_post["removed_datetime"] = (
                            f"{datetime.now(timezone.utc)}"
                        )
                        removed_posts.append(tickers_post)
                        continue
                    ticker_stream.save(tickers_post)
                    ticker_checkpoint.save(msg_id)
            print("ticker identification done\n\n\n")

            # Step 3: Add newly identified tickers to be consumed at scraping service
            if all_tickers:
                aliases = ticker_service.get_aliases(list(all_tickers))

                for ticker, data in aliases.items():
                    redis_client.hset(
                        "all_identified_tickers", ticker, json.dumps(data)
                    )

            # Step 4: Event Identification
            event_last_id = event_checkpoint.load()
            ticker_entries = ticker_stream.read(
                last_id=event_last_id, count=10, block_ms=5000
            )
            if not ticker_entries:
                continue
            for _, messages in ticker_entries:
                for msg_id, data in messages:
                    event_data = eventidentifier.analyse_event(data)
                    if not event_data:
                        continue

                    ticker_metadata = event_data.get("ticker_metadata", {})

                    # Collect tickers with no event info
                    tickers_to_remove = {
                        ticker: info
                        for ticker, info in ticker_metadata.items()
                        if info.get("event_type") is None
                        and info.get("event_proposal") is None
                    }

                    # Remove these tickers from the original ticker_metadata
                    for ticker in tickers_to_remove:
                        ticker_metadata.pop(ticker)

                    # If any tickers were removed, store them as one removed_post
                    if tickers_to_remove:
                        removed_post = {
                            **event_data,  # copy the rest of the event_data
                            "ticker_metadata": tickers_to_remove,
                            "removed_reason": "No event identified",
                            "removed_datetime": f"{datetime.now(timezone.utc)}",
                        }
                        removed_posts.append(removed_post)

                    # Save remaining tickers to event_stream
                    if ticker_metadata:
                        event_data["ticker_metadata"] = ticker_metadata
                        all_tickers.update(ticker_metadata.keys())
                        event_stream.save(event_data)
                        event_checkpoint.save(msg_id)
            print("event identification done\n\n\n")

            # Step 5: Credibility - jiayen
            # first load credibility checkpoint - if nothing processed yet, it will be 0-0
            # consume from event_stream and push to credibility_stream

            # Step 6: Sentiment Analysis - jiayen
            # first load Sentiment checkpoint - if nothing processed yet, it will be 0-0
            # consume from event_stream and push to sentiment_stream

            # Step 7: Vectorisation - joshua
            # first load Vectorisation checkpoint - if nothing processed yet, it will be 0-0
            # consume from sentiment_stream and save to vectorDB
            vector_last_id = vectorisation_checkpoint.load()
            sentiment_entries = sentiment_stream.read(
                last_id=vector_last_id, count=10, block_ms=5000
            )

            if sentiment_entries:
                for _, messages in sentiment_entries:
                    for msg_id, data in messages:
                        try:
                            payload = NewsAnalysisPayload(**data)
                            await vectorisation_service.ingest_docs(payload)
                            vectorisation_checkpoint.save(msg_id)
                        except Exception as e:
                            print(f"Error in Vectorisation Step: {e}")

                print("🎉 Saved to Qdrant")

    except redis.exceptions.ConnectionError as e:
        print(f"[Error] Redis connection failed: {e}")
    except json.JSONDecodeError as e:
        print(f"[Error] JSON decoding failed: {e}")
    except Exception as e:
        print(f"[Error] Unexpected error: {e}")
    except KeyboardInterrupt as e:
        print(f"Exiting program now...")

    finally:
        try:
            if ticker_service.new_alias_count > 0:
                print(f"[S3 Save] — {ticker_service.new_alias_count} new aliases added")
                bucket.write_text(
                    json.dumps(ticker_service.alias_to_canonical, indent=2),
                    env_config.aws_bucket_alias_key,
                )
            if removed_posts:
                bucket.write_text(
                    json.dumps(removed_posts, indent=2),
                    env_config.aws_bucket_removed_key,
                )

            if eventidentifier.event_list and eventidentifier.neweventcount > 0:
                bucket.write_text(
                    json.dumps(eventidentifier.event_list, indent=2),
                    env_config.aws_bucket_events_key,
                )
        except Exception as e:
            print(f"[Error] Failed during cleanup: {e}")
