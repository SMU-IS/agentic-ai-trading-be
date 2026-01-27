import json
from operator import itemgetter
from typing import List

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

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

        self.chain = (
            {
                "context": RunnableLambda(self.fetch_news_context),
                "query": itemgetter("query"),
            }
            | self.prompt
            | self.llm
            | StrOutputParser()
        )

    async def fetch_news_context(self, inputs: dict):
        """
        Calls the external news-analysis service to retrieve news context.
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

            articles = data.get("results", [])

            if not articles:
                return "No relevant news found for the requested tickers."

            context = "\n\n".join(
                [
                    f"Headline: {d['headline']}\nContent: {d['content_preview']}"
                    for d in articles
                ]
            )
            return context

    async def get_answer_stream(self, query: str, tickers: List[str]):
        """
        Streams response to FE.
        """

        inputs = {"query": query, "tickers": tickers}

        try:
            async for chunk in self.chain.astream(inputs):
                if chunk:
                    yield f"data: {json.dumps({'token': chunk})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"
