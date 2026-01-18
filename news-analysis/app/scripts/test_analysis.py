# scripts/test_analysis.py
import json
from app.services.sentiment import SentimentAnalyzer

if __name__ == "__main__":
    sentiment_analyzer = SentimentAnalyzer()
    
    with open("./app/data/cleaned_dummy.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle single dict or list of dicts
    if isinstance(data, dict):
        data = [data]
    
    analysed_data = []
    for item in data:
        result = sentiment_analyzer.process(item)
        analysed_data.append(result)

    with open("./app/data/analysed_dummy.json", "w", encoding="utf-8") as f:
        json.dump(analysed_data, f, ensure_ascii=False, indent=2)

    print("✅ Analysed data saved to ./app/data/analysed_dummy.json")