import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import redis

from app.core.config import env_config
from app.schemas.compiled_news_payload import NewsAnalysisPayload, NewsMetadata
from app.scripts.aws_bucket_access import AWSBucket
from app.scripts.checkpoint import RedisCheckpoint
from app.scripts.storage import RedisStreamStorage
from app.services import (
    EventIdentifierService,
    PreprocessingService,
    LLMSentimentService,
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


def transform_to_payload(data: Dict[str, Any]) -> Optional[NewsAnalysisPayload]:
    """
    Transform pipeline data to NewsAnalysisPayload for vectorisation.

    Args:
        data: Pipeline data with content, ticker_metadata, and sentiment_analysis

    Returns:
        NewsAnalysisPayload ready for vectorisation, or None if transformation fails
    """
    try:
        # Extract content
        content = data.get('content', {})
        clean_text = (
            content.get('clean_combined_withurl', '') or
            content.get('clean_combined_withouturl', '') or
            content.get('clean_combined', '') or
            ''
        )
        headline = (
            content.get('clean_title', '') or
            data.get('clean_title', '') or
            'No headline'
        )

        # Extract ticker metadata and list of tickers
        ticker_metadata = data.get('ticker_metadata', {})
        tickers = list(ticker_metadata.keys())

        # Get primary event type (from first ticker or default)
        event_type = 'Unknown'
        if ticker_metadata:
            first_ticker = next(iter(ticker_metadata.values()), {})
            event_type = first_ticker.get('event_type', 'Unknown') or 'Unknown'

        # Extract sentiment analysis
        sentiment_analysis = data.get('sentiment_analysis', {})
        overall_score = sentiment_analysis.get('overall_sentiment_score', 0.0)
        overall_label = sentiment_analysis.get('overall_sentiment_label', 'neutral')

        # Calculate average confidence from per-ticker sentiments
        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})
        confidences = [
            ts.get('confidence', 0.5)
            for ts in ticker_sentiments.values()
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Extract post metadata
        post_id = data.get('Post_ID', data.get('id', f"post_{datetime.now().timestamp()}"))
        source = data.get('subreddit', 'reddit')
        url = data.get('URL', data.get('url', ''))
        author = data.get('Author', data.get('author', None))

        # Parse timestamp
        created_utc = data.get('Created_UTC', data.get('created_utc', None))
        if created_utc:
            if isinstance(created_utc, (int, float)):
                timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            else:
                timestamp = datetime.fromisoformat(str(created_utc).replace('Z', '+00:00'))
        else:
            timestamp = datetime.now(timezone.utc)

        # Build metadata
        metadata = NewsMetadata(
            article_id=post_id,
            tickers=tickers,
            timestamp=timestamp,
            source_domain=f"reddit.com/r/{source}" if source else "reddit.com",
            event_type=event_type,
            sentiment_score=overall_score,
            sentiment_label=overall_label,
            sentiment_confidence=avg_confidence,
            headline=headline,
            text_content=clean_text,
            url=url,
            author=author,
            ticker_metadata=ticker_metadata,
            sentiment_analysis=sentiment_analysis
        )

        return NewsAnalysisPayload(id=post_id, metadata=metadata)

    except Exception as e:
        print(f"[Error] Failed to transform data to payload: {e}")
        return None


async def run_pipeline():
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

            # Step 5: Sentiment Analysis (LLM-based using Gemini)
            sentiment_last_id = sentiment_checkpoint.load()
            event_entries = event_stream.read(
                last_id=sentiment_last_id, count=10, block_ms=5000
            )
            if not event_entries:
                continue
            for _, messages in event_entries:
                for msg_id, data in messages:
                    sentiment_result = await sentiment_service.analyse(data)
                    sentiment_stream.save(sentiment_result)
                    sentiment_checkpoint.save(msg_id)
            print("sentiment analysis done\n\n\n")

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
                            # Transform pipeline data to NewsAnalysisPayload
                            payload = transform_to_payload(data)
                            if payload:
                                await vectorisation_service.ingest_docs(payload)
                                vectorisation_checkpoint.save(msg_id)
                            else:
                                print(f"[Warning] Skipping message {msg_id}: transformation failed")
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


if __name__ == "__main__":
    asyncio.run(run_pipeline())
