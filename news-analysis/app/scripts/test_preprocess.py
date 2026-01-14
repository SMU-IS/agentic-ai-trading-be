# scripts/test_preprocess.py
import json
from app.services.preprocesser import PreprocessingService

if __name__ == "__main__":
    preprocessor = PreprocessingService()
    with open("dummy.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    processed_data = preprocessor.process_input(data)

    with open("cleaned_dummy.json", "w", encoding="utf-8") as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)

    print("✅ Processed data saved to cleaned_dummy.json")
