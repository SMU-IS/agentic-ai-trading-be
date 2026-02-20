import asyncio
import json
from datetime import datetime, timezone

import httpx
import redis
from pydantic import ValidationError
from redis import exceptions

from app.core.config import env_config
from app.core.logger import logger
from app.scripts.aws_bucket_access import AWSBucket
from app.scripts.checkpoint import RedisCheckpoint
from app.scripts.storage import RedisStreamStorage
from app.services import (
    EventIdentifierService,
    LLMSentimentService,
    PreprocessingService,
    TickerIdentificationService,
    VectorisationService,
)

# =============================================================================
# RATE LIMITING CONFIGURATION (for testing with API rate limits)
# Set ENABLE_RATE_LIMITING = False for production with paid API tier
# =============================================================================
# Enable/disable rate limiting (False = real-time processing for production)
ENABLE_RATE_LIMITING = True

# Delay between each LLM API call in seconds (only when rate limiting enabled)
SENTIMENT_API_DELAY_SECONDS = 3.0  # 3 seconds between calls

# Number of items to process per pipeline cycle (lower = slower but safer)
SENTIMENT_BATCH_SIZE = 50  # Process 50 posts per cycle when rate limiting
# =============================================================================


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
# event stream to be consumed by sentiment service
event_stream = RedisStreamStorage(env_config.redis_event_stream, redis_client)
# sentiment stream to be consumed by vectorisation service
sentiment_stream = RedisStreamStorage(env_config.redis_sentiment_stream, redis_client)
# LLM-based sentiment analysis service using Gemini
sentiment_service = LLMSentimentService()


# all tickers set to be updated and sent to scraping service
all_tickers = set()
removed_posts = []


# load files from AWS bucket
cleaned_tickers = json.loads(bucket.read_text(env_config.aws_bucket_cleaned_key))
alias_to_canonical = json.loads(bucket.read_text(env_config.aws_bucket_alias_key))
events_types = json.loads(bucket.read_text(env_config.aws_bucket_events_key))


# def transform_to_payload(data: Dict[str, Any]) -> Optional[NewsAnalysisPayload]:
#     """
#     Transform pipeline data to NewsAnalysisPayload for vectorisation.

#     Args:
#         data: Pipeline data with content, ticker_metadata, and sentiment_analysis

#     Returns:
#         NewsAnalysisPayload ready for vectorisation, or None if transformation fails
#     """
#     try:
#         # Extract content
#         content = data.get("content", {})
#         clean_text = (
#             content.get("clean_combined_withurl", "")
#             or content.get("clean_combined_withouturl", "")
#             or content.get("clean_combined", "")
#             or ""
#         )
#         headline = (
#             content.get("clean_title", "")
#             or data.get("clean_title", "")
#             or "No headline"
#         )

#         # Extract ticker metadata and list of tickers
#         ticker_metadata = data.get("ticker_metadata", {})
#         tickers = list(ticker_metadata.keys())

#         # Get primary event type (from first ticker or default)
#         event_type = "Unknown"
#         if ticker_metadata:
#             first_ticker = next(iter(ticker_metadata.values()), {})
#             event_type = first_ticker.get("event_type", "Unknown") or "Unknown"

#         # Extract sentiment analysis
#         sentiment_analysis = data.get("sentiment_analysis", {})
#         overall_score = sentiment_analysis.get("overall_sentiment_score", 0.0)
#         overall_label = sentiment_analysis.get("overall_sentiment_label", "neutral")

#         # Calculate average confidence from per-ticker sentiments
#         ticker_sentiments = sentiment_analysis.get("ticker_sentiments", {})
#         confidences = [ts.get("confidence", 0.5) for ts in ticker_sentiments.values()]
#         avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

#         # Extract post metadata
#         post_id = data.get(
#             "Post_ID", data.get("id", f"post_{datetime.now().timestamp()}")
#         )
#         source = data.get("subreddit", "reddit")
#         url = data.get("URL", data.get("url", ""))
#         author = data.get("Author", data.get("author", None))

#         # Parse timestamp
#         created_utc = data.get("Created_UTC", data.get("created_utc", None))
#         if created_utc:
#             if isinstance(created_utc, (int, float)):
#                 timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc)
#             else:
#                 timestamp = datetime.fromisoformat(
#                     str(created_utc).replace("Z", "+00:00")
#                 )
#         else:
#             timestamp = datetime.now(timezone.utc)

#         # Build metadata
#         metadata = NewsMetadata(
#             article_id=post_id,
#             tickers=tickers,
#             timestamp=timestamp,
#             source_domain=f"reddit.com/r/{source}" if source else "reddit.com",
#             event_type=event_type,
#             sentiment_score=overall_score,
#             sentiment_label=overall_label,
#             sentiment_confidence=avg_confidence,
#             headline=headline,
#             text_content=clean_text,
#             url=url,
#             author=author,
#             ticker_metadata=ticker_metadata,
#             sentiment_analysis=sentiment_analysis,
#         )

#         return NewsAnalysisPayload(id=post_id, metadata=metadata)

#     except Exception as e:
#         print(f"[Error] Failed to transform data to payload: {e}")
#         return None


async def run_pipeline():
    logger.info("💨 Starting orchestration pipeline...")

    # Service Initialisation
    preproc_checkpoint = RedisCheckpoint("preprocess", redis_client)
    ticker_checkpoint = RedisCheckpoint("tickeridentification", redis_client)
    event_checkpoint = RedisCheckpoint("eventidentification", redis_client)
    sentiment_checkpoint = RedisCheckpoint("sentiment", redis_client)
    vectorisation_checkpoint = RedisCheckpoint("vectorisation", redis_client)

    # Service Initialisation
    preprocessor = PreprocessingService()

    eventidentifier = EventIdentifierService(event_list=events_types)
    ticker_service = TickerIdentificationService(
        cleaned_tickers=cleaned_tickers,
        alias_to_canonical=alias_to_canonical,
    )

    vectorisation_service = VectorisationService()
    await vectorisation_service.ensure_indexes()

    # # Clear streams for testing
    # preprocessing_stream.clear_stream()
    # ticker_stream.clear_stream()
    # event_stream.clear_stream()
    # sentiment_stream.clear_stream()
    # redis_client.delete("all_identified_tickers")

    try:
        # Step 1: Consume scrapped data from Reddit stream
        preproc_last_id = preproc_checkpoint.load()
        reddit_entries = reddit_stream.read(
            last_id=preproc_last_id, count=10, block_ms=5000
        )
        if reddit_entries:
            for _, messages in reddit_entries:
                for msg_id, data in messages:
                    post_content = data.get("data", data)
                    processed = preprocessor.preprocess_post(post_content)
                    preprocessing_stream.save(processed)
                    preproc_checkpoint.save(msg_id)
                    reddit_stream.delete(msg_id)
                    logger.info(f"{msg_id} deleted from reddit stream.")
        logger.info("preprocessing done\n\n\n")

        # Step 2: Extract tickers
        ticker_processed_count = 0
        ticker_last_id = ticker_checkpoint.load()
        preproc_entries = preprocessing_stream.read(
            last_id=ticker_last_id, count=10, block_ms=5000
        )
        if preproc_entries:
            for _, messages in preproc_entries:
                for msg_id, data in messages:
                    # Rate limiting: add delay between API calls (for testing)
                    if ENABLE_RATE_LIMITING and ticker_processed_count > 0:
                        logger.info(
                            f"[Rate Limit] Waiting {SENTIMENT_API_DELAY_SECONDS}s before next API call..."
                        )
                        await asyncio.sleep(SENTIMENT_API_DELAY_SECONDS)
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
                    preprocessing_stream.delete(msg_id)
                    logger.info(f"{msg_id} deleted from preprocessing stream.")
                    ticker_processed_count += 1
        logger.info("ticker identification done\n\n\n")

        # Step 3: Event Identification
        event_last_id = event_checkpoint.load()
        ticker_entries = ticker_stream.read(
            last_id=event_last_id, count=10, block_ms=5000
        )
        if ticker_entries:
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
                        ticker_stream.delete(msg_id)
                        logger.info(f"{msg_id} deleted from ticker stream.")

        logger.info("event identification done\n\n\n")

        # Step 4: Add newly identified tickers to be consumed at scraping service (Only relevant tickers with event)
        if all_tickers:
            aliases = ticker_service.get_aliases(list(all_tickers))

            for ticker, data in aliases.items():
                redis_client.hset("all_identified_tickers", ticker, json.dumps(data))
            logger.info("Successfully updated tickers list\n\n\n")
            all_tickers.clear()

        # Step 5: Sentiment Analysis (LLM-based using Gemini)
        # Rate limiting: process fewer items with delays between calls for testing
        # Set ENABLE_RATE_LIMITING = False for real-time production processing
        sentiment_last_id = sentiment_checkpoint.load()

        # Adjust batch size based on rate limiting mode
        read_count = SENTIMENT_BATCH_SIZE if ENABLE_RATE_LIMITING else 10

        event_entries = event_stream.read(
            last_id=sentiment_last_id, count=10, block_ms=5000
        )
        if event_entries:
            processed_count = 0
            for _, messages in event_entries:
                for msg_id, data in messages:
                    # Rate limiting: add delay between API calls (for testing)
                    if ENABLE_RATE_LIMITING and processed_count > 0:
                        logger.info(
                            f"[Rate Limit] Waiting {SENTIMENT_API_DELAY_SECONDS}s before next API call..."
                        )
                        await asyncio.sleep(SENTIMENT_API_DELAY_SECONDS)

                    sentiment_result = await sentiment_service.analyse(data)
                    sentiment_stream.save(sentiment_result)
                    sentiment_checkpoint.save(msg_id)
                    event_stream.delete(msg_id)
                    logger.info(f"{msg_id} deleted from event stream.")

                    processed_count += 1

                    if ENABLE_RATE_LIMITING:
                        logger.info(
                            f"[Rate Limit] Processed {processed_count}/{read_count} items"
                        )

        logger.info("sentiment analysis done\n\n\n")

        # Step 6: Vectorisation
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
                        payload_dict = {"id": msg_id, "fields": data}
                        vectorisation_url = f"{env_config.vectorise_and_save_to_qdrant}"
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                vectorisation_url, json=payload_dict
                            )
                            response.raise_for_status()
                            response_status = response.json()
                            logger.info(f"✅ Vectorised {response_status}")

                        vectorisation_checkpoint.save(msg_id)
                        sentiment_stream.delete(msg_id)

                        # payload = RedditSourcePayload(**payload_dict)
                        # if payload:
                        #     await vectorisation_service.get_sanitised_news_payload(
                        #         payload
                        #     )
                        #     vectorisation_checkpoint.save(msg_id)
                        #     sentiment_stream.delete(msg_id)

                    except ValidationError as e:
                        # Print the post ID and missing fields
                        missing_fields = [err["loc"] for err in e.errors()]
                        logger.warning(
                            f"[ValidationError] Post ID {data.get('id')} is missing fields: {missing_fields}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[Error] Unexpected error in Vectorisation Step for Post ID {data.get('id')}: {e}"
                        )

            logger.info("🎉 Saved to Qdrant")

    except exceptions.ConnectionError as e:
        logger.error(f"[Error] Redis connection failed: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"[Error] JSON decoding failed: {e}")
    except Exception as e:
        logger.error(f"[Error] Unexpected error: {e}")
    except KeyboardInterrupt as e:
        logger.info(f"Exiting program now... {e}")

    finally:
        try:
            if ticker_service.new_alias_count > 0:
                logger.info(
                    f"[S3 Save] — {ticker_service.new_alias_count} new aliases added"
                )
                bucket.write_text(
                    json.dumps(ticker_service.alias_to_canonical, indent=2),
                    env_config.aws_bucket_alias_key,
                )
                logger.info("Successfully updated alias mapping\n\n\n")

            if removed_posts:
                bucket.write_text(
                    json.dumps(removed_posts, indent=2),
                    env_config.aws_bucket_removed_key,
                )
                logger.info("Successfully updated removed post list\n\n\n")

            if eventidentifier.event_list and eventidentifier.neweventcount > 0:
                bucket.write_text(
                    json.dumps(eventidentifier.event_list, indent=2),
                    env_config.aws_bucket_events_key,
                )
                logger.info("Successfully updated event type list\n\n\n")

            if ticker_service.cleaned_tickers and ticker_service.new_type_count > 0:
                bucket.write_text(
                    json.dumps(ticker_service.cleaned_tickers, indent=2),
                    env_config.aws_bucket_cleaned_key,
                )
                logger.info("Successfully updated cleaned ticker list\n\n\n")

            if all_tickers:
                aliases = ticker_service.get_aliases(list(all_tickers))

                for ticker, data in aliases.items():
                    redis_client.hset(
                        "all_identified_tickers", ticker, json.dumps(data)
                    )

                logger.info("Successfully updated tickers list\n\n\n")
                all_tickers.clear()

        except Exception as e:
            logger.error(f"[Error] Failed during cleanup: {e}")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
