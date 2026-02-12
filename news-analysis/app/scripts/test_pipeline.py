"""
Updated Test Script with Proper Redis Stream Consumption
File: news-analysis/app/scripts/test_pipeline.py

Demonstrates proper sequential processing through the pipeline
"""

import asyncio
import json
import logging

import redis
from app.core.config import env_config
from app.scripts.aws_bucket_access import AWSBucket
from app.scripts.storage import RedisStreamStorage
from app.services._01_preprocesser import PreprocessingService
from app.services._02_ticker_identification import TickerIdentificationService
from app.services._03_event_identification import EventIdentifierService
from app.services._04_credibility import CredibilityService
from app.services._05_sentiment import sentiment_service

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_test_pipeline():
    """
    Test pipeline with proper sequential processing

    Flow: reddit → preproc → ticker → event → credibility/sentiment
    """

    logger.info("=" * 80)
    logger.info("STARTING TEST PIPELINE")
    logger.info("=" * 80)

    # Setup Redis
    redis_client = redis.Redis(
        host=env_config.redis_host,
        port=env_config.redis_port,
        password=env_config.redis_password,
        decode_responses=True,
    )

    # Setup S3
    bucket = AWSBucket()

    # Initialize streams
    streams = {
        "reddit": RedisStreamStorage("reddit_stream", redis_client),
        "preproc": RedisStreamStorage("preproc_stream", redis_client),
        "ticker": RedisStreamStorage("ticker_stream", redis_client),
        "event": RedisStreamStorage("event_stream", redis_client),
        "credibility": RedisStreamStorage("credibility_stream", redis_client),
        "sentiment": RedisStreamStorage("sentiment_stream", redis_client),
    }

    # Load configuration
    logger.info("Loading configuration from S3...")
    CLEANED_KEY = "data/processed/cleaned_tickers.json"
    ALIAS_KEY = "data/processed/alias_to_canonical.json"
    EVENTS_KEY = "data/config/financial_event_types.json"

    cleaned_tickers = json.loads(bucket.read_text(CLEANED_KEY))
    alias_to_canonical = json.loads(bucket.read_text(ALIAS_KEY))
    events_types = json.loads(bucket.read_text(EVENTS_KEY))

    # Initialize services
    logger.info("Initializing services...")
    preprocessor = PreprocessingService()
    ticker_service = TickerIdentificationService(
        cleaned_tickers=cleaned_tickers,
        alias_to_canonical=alias_to_canonical,
    )
    event_identifier = EventIdentifierService(event_list=events_types)
    credibility_service = CredibilityService(enable_llm=False)

    # Clear downstream streams (keep reddit stream intact)
    logger.info("Clearing downstream streams...")
    for name, stream in streams.items():
        if name != "reddit":
            stream.clear_stream()

    # Track statistics
    stats = {
        "reddit_consumed": 0,
        "preprocessed": 0,
        "ticker_identified": 0,
        "events_found": 0,
        "credibility_analyzed": 0,
        "sentiment_analyzed": 0,
    }

    all_tickers = set()

    # STAGE 1: Preprocessing
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 1: PREPROCESSING")
    logger.info("=" * 80)

    entries = streams["reddit"].read(last_id="0-0", count=50, block_ms=5000)

    for _, messages in entries:
        for msg_id, data in messages:
            try:
                post_content = data.get("data", data)
                processed = preprocessor.preprocess_post(post_content)
                streams["preproc"].save(processed)

                stats["reddit_consumed"] += 1
                stats["preprocessed"] += 1

            except Exception as e:
                logger.error(f"Preprocessing error for {msg_id}: {e}")

    logger.info(f"✓ Preprocessed {stats['preprocessed']} posts")

    # STAGE 2: Ticker Identification
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 2: TICKER IDENTIFICATION")
    logger.info("=" * 80)

    preproc_entries = streams["preproc"].read(last_id="0-0", count=50, block_ms=5000)

    for _, messages in preproc_entries:
        for msg_id, data in messages:
            try:
                post_content = data.get("data", data)
                tickers_post = ticker_service.process_post(post_content)

                if not tickers_post:
                    # No tickers found - still pass to next stage
                    streams["ticker"].save(post_content)
                    continue

                streams["ticker"].save(tickers_post)

                # Extract ticker metadata
                ticker_metadata = tickers_post.get("ticker_metadata", {})
                if ticker_metadata:
                    simple_ticker_metadata = {
                        ticker: info["OfficialName"]
                        for ticker, info in ticker_metadata.items()
                    }

                    redis_client.hset(
                        "ticker_to_official_name", mapping=simple_ticker_metadata
                    )

                    all_tickers.update(simple_ticker_metadata.keys())
                    stats["ticker_identified"] += len(simple_ticker_metadata)

            except Exception as e:
                logger.error(f"Ticker identification error for {msg_id}: {e}")

    logger.info(f"✓ Identified {stats['ticker_identified']} unique tickers")

    # Save tickers to Redis set
    if all_tickers:
        redis_client.sadd("all_identified_tickers", *all_tickers)
        logger.info(f"✓ Added {len(all_tickers)} tickers to Redis set")

    # STAGE 3: Event Identification
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3: EVENT IDENTIFICATION")
    logger.info("=" * 80)

    ticker_entries = streams["ticker"].read(last_id="0-0", count=50, block_ms=5000)

    for _, messages in ticker_entries:
        for msg_id, data in messages:
            try:
                post_content = data.get("data", data)
                event_data = event_identifier.analyse_event(post_content)
                streams["event"].save(event_data)

                # Check if events were found
                if event_data.get("event_metadata"):
                    stats["events_found"] += len(event_data["event_metadata"])

            except Exception as e:
                logger.error(f"Event identification error for {msg_id}: {e}")

    logger.info(f"✓ Identified {stats['events_found']} events")

    # STAGE 4: Credibility Analysis
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 4: CREDIBILITY ANALYSIS")
    logger.info("=" * 80)

    event_entries = streams["event"].read(last_id="0-0", count=50, block_ms=5000)

    # Process credibility first
    credibility_enriched = []
    for _, messages in event_entries:
        for msg_id, data in messages:
            try:
                post_content = data.get("data", data)
                # Analyze credibility
                cred_result = credibility_service.analyse(post_content)
                streams["credibility"].save(cred_result)
                credibility_enriched.append(cred_result)
                stats["credibility_analyzed"] += 1
            except Exception as e:
                logger.error(f"Credibility error for {msg_id}: {e}")

    logger.info(f"✓ Analyzed credibility for {stats['credibility_analyzed']} items")

    # STAGE 5: Sentiment Analysis (consumes credibility-enriched data)
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 5: SENTIMENT ANALYSIS")
    logger.info("=" * 80)

    if credibility_enriched:
        logger.info(
            f"Processing {len(credibility_enriched)} credibility-enriched items..."
        )

        # Process sentiment on credibility-enriched data
        sentiment_results = sentiment_service.process_batch(credibility_enriched)
        stats["sentiment_analyzed"] = len(sentiment_results)

        # Save to sentiment stream
        for item in sentiment_results:
            streams["sentiment"].save(item)

        logger.info(f"✓ Analyzed sentiment for {stats['sentiment_analyzed']} items")
    else:
        logger.warning("No items to process for sentiment analysis")

    # RESULTS SUMMARY
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE RESULTS")
    logger.info("=" * 80)

    for stage, count in stats.items():
        logger.info(f"{stage:<25}: {count}")

    # View sample outputs
    logger.info("\n" + "=" * 80)
    logger.info("SAMPLE OUTPUTS")
    logger.info("=" * 80)

    # Show sample from each stream
    stream_samples = {
        "Preprocessed Data": streams["preproc"],
        "Ticker Identified": streams["ticker"],
        "Events Found": streams["event"],
        "Credibility Scores": streams["credibility"],
        "Sentiment Scores": streams["sentiment"],
    }

    for name, stream in stream_samples.items():
        logger.info(f"\n--- {name} (first 2 items) ---")
        entries = stream.read(last_id="0-0", count=2, block_ms=1000)

        if not entries:
            logger.info("  (empty)")
            continue

        for _, messages in entries:
            for msg_id, data in messages:
                # Show only relevant fields
                sample = {}
                if "Post_ID" in data:
                    sample["Post_ID"] = data["Post_ID"]
                if "identified_tickers" in data:
                    sample["tickers"] = data["identified_tickers"]
                if "event_metadata" in data:
                    sample["events"] = list(data["event_metadata"].keys())
                if "credibility_score" in data:
                    sample["credibility"] = round(data["credibility_score"], 3)
                if "sentiment_label" in data:
                    sample["sentiment"] = data["sentiment_label"]

                logger.info(f"  {json.dumps(sample, indent=2)}")

    # Final statistics
    logger.info("\n" + "=" * 80)
    logger.info("REDIS STATISTICS")
    logger.info("=" * 80)

    # Stream lengths
    for name, stream in streams.items():
        try:
            info = redis_client.xinfo_stream(stream.stream_name)
            length = info.get("length", 0)
            logger.info(f"{name}_stream: {length} items")
        except Exception as e:
            logger.info(f"{name}_stream: {e}")

    # Ticker mappings
    ticker_count = redis_client.hlen("ticker_to_official_name")
    logger.info(f"ticker_to_official_name: {ticker_count} mappings")

    all_tickers_count = redis_client.scard("all_identified_tickers")
    logger.info(f"all_identified_tickers: {all_tickers_count} tickers")

    logger.info("\n" + "=" * 80)
    logger.info("TEST PIPELINE COMPLETED")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_test_pipeline())
