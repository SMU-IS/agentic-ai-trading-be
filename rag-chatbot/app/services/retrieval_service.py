import json
from typing import List

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.core.config import env_config


class RetrievalService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.qdrant_db_url = env_config.news_analysis_query_url
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a financial analyst. Use the following news context to answer the user.\n\nContext:\n{context}",
                ),
                ("human", "{query}"),
            ]
        )

        self.rag_chain: Runnable = self.prompt | self.llm | StrOutputParser()

    async def _fetch_news_context_and_results(self, inputs: dict):
        """
        Calls the external news-analysis service to retrieve news context and results.
        """

        payload = {
            "query": inputs["query"],
            "limit": 5,
            "ticker_filter": inputs.get("tickers", []),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.qdrant_db_url, json=payload)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                context = "No relevant news found for the requested tickers."
            else:
                context = "\n\n".join(
                    [
                        f"Headline: {d.get('headline', 'No headline')}\nContent: {d.get('content_preview', 'No content preview')}"
                        for d in results
                    ]
                )
            return {"context": context, "results": results}

    async def get_answer_stream(self, query: str, tickers: List[str]):
        """
        Streams response to FE.
        """

        inputs = {"query": query, "tickers": tickers}

        try:
            news_context = await self._fetch_news_context_and_results(inputs)
            context, results = news_context["context"], news_context["results"]
            chain_input = {"context": context, "query": query}

            async for chunk in self.rag_chain.astream(chain_input):
                if chunk:
                    yield f"data: {json.dumps({'token': chunk})}\n\n"

            if results:
                citations = [
                    {
                        "headline": result.get("headline"),
                        "url": result.get("metadata", {}).get("url", "No URL provided"),
                    }
                    for result in results
                ]
                yield f"data: {json.dumps({'citations': citations})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"
