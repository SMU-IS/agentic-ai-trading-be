# scripts/test_ticker_identification.py
import json
import os
from app.services._02_ticker_identification import TickerIdentificationService

if __name__ == "__main__":
    # Initialize your ticker identification service
    current_dir = os.path.dirname(__file__)
    cleaned_tickers_path = os.path.join(current_dir, '..', 'data', 'cleaned_tickers.json')
    alias_to_canonical_path = os.path.join(current_dir, '..', 'data', 'alias_to_canonical.json')
    service = TickerIdentificationService(
        cleaned_tickers_path=cleaned_tickers_path,
        alias_to_canonical_path=alias_to_canonical_path
    )

    # Set up file paths relative to this script
    current_dir = os.path.dirname(__file__)
    cleaned_dummy_path = os.path.join(current_dir, '..', 'data', 'cleaned_dummy.json')
    identified_tickers_path = os.path.join(current_dir, '..', 'data', 'identified_tickers.json')

    # Load your test data
    with open(cleaned_dummy_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Process the data to identify tickers
    identified_tickers = service.process_input(data)

    # Save the results to a new file
    with open(identified_tickers_path, "w", encoding="utf-8") as f:
        json.dump(identified_tickers, f, ensure_ascii=False, indent=2)

    print(f"✅ Identified tickers saved to {identified_tickers_path}")
