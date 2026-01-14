import asyncio
import json
from pathlib import Path
from typing import Dict, List

from app.core.config import env_config
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate


class CredibilityService:
    def __init__(
        self,
        model_provider: str = "ollama",  # TODO: Remove hardcode
        model_name: str = env_config.large_language_model,
    ):
        self.llm: BaseChatModel = init_chat_model(
            model=model_name,
            model_provider=model_provider,
            temperature=0,
            model_kwargs={"format": "json"},
        )
        self.parser = JsonOutputParser()
        self.source_weights = {
            "reuters.com": 0.95,
            "bloomberg.com": 0.95,
            "ft.com": 0.95,
            "wsj.com": 0.95,
            "cnbc.com": 0.85,
            "reddit.com/r/investing": 0.70,
            "reddit.com/r/stocks": 0.60,
            "reddit.com/r/wallstreetbets": 0.30,
        }

    def _get_base_score(self, item: Dict) -> float:
        domain = item.get("Domain", "")
        subreddit = item.get("Subreddit", "")
        key = f"reddit.com/r/{subreddit}" if domain == "reddit.com" else domain
        base = self.source_weights.get(key, 0.50)

        if domain == "reddit.com":
            base *= item.get("Upvote_Ratio", 1.0)

        return round(base, 2)

    async def process_data(self, data: List[Dict], batch_size: int = 5) -> List[Dict]:
        """
        Processes news items in parallel batches to optimize speed.
        """

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a linguistic pattern extractor. Analyze text for factual indicators. Output ONLY JSON.",
                ),
                (
                    "user",
                    "Analyze news snippet for credibility: {text}\nReturn JSON: factual_accuracy_score (0-1), is_speculative (bool), reasoning.",
                ),
            ]
        )

        chain = prompt | self.llm | self.parser
        results = []

        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            batch_inputs = [
                {
                    "text": item.get("clean_combined")
                    or f"{item.get('Title', '')} {item.get('Body', '')}"
                }
                for item in batch
            ]

            try:
                batch_analyses = await chain.abatch(batch_inputs)

            except Exception as e:
                batch_analyses = [
                    {
                        "factual_accuracy_score": 0.5,
                        "is_speculative": True,
                        "reasoning": f"Batch Error: {str(e)[:30]}",
                    }
                ] * len(batch)

            for item, llm_res in zip(batch, batch_analyses):
                base_score = self._get_base_score(item)

                # 60% Source Reliability / 40% LLM Analysis
                final_score = (base_score * 0.6) + (
                    llm_res.get("factual_accuracy_score", 0.5) * 0.4
                )

                item["credibility_score"] = round(final_score, 2)
                item["credibility_metadata"] = llm_res
                results.append(item)

        return results


# TODO: To be removed
async def main():
    print("--- STARTING ASYNC CREDIBILITY ANALYSIS (Step 4) ---")

    current_dir = Path(__file__).parent
    data_path = current_dir.parent / "data" / "cleaned_dummy.json"
    with open(data_path, "r") as f:
        data = json.load(f)

    credibility_service = CredibilityService()
    results = await credibility_service.process_data(data)
    print(json.dumps(results[:2], indent=2))
    print(f"--- Processed {len(results)} items concurrently ---")


if __name__ == "__main__":
    asyncio.run(main())
