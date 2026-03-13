import json
import os
import re
from typing import List, Optional, Type, Any, Union

from pydantic import BaseModel
from langchain_perplexity import ChatPerplexity
from langchain_groq import ChatGroq

from src.services.json_parser import safe_parse
from langchain_core.messages import HumanMessage, SystemMessage  # Add this import
from src.config import settings

class LLMService:
    def __init__(self):
        self.model = settings.model
        self.provider = settings.llm_provider
        self.llm = self._init_llm()

    # Provider toggle
    def _init_llm(self) -> Union[ChatGroq, ChatPerplexity]:
        if self.provider == "groq":
            key = settings.groq_api_key
            if not key:
                raise ValueError("GROQ_API_KEY required for Groq")
            return ChatGroq(
                groq_api_key=key,
                model=self.model,
                temperature=0.1,
            )
        elif self.provider == "perplexity":
            key = settings.pplx_api_key
            if not key:
                raise ValueError("PPLX_API_KEY required for Perplexity")
            return ChatPerplexity(
                pplx_api_key=key,
                model=self.model,
                temperature=0.1,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
            

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        result = await self.llm.ainvoke(messages)
        return result.content

    async def generate_list(self, prompt: str) -> List[dict[str, Any]]:
        response = await self.generate(prompt)
        return self.parse_json_list(response)

    async def generate_parse_json(
        self,
        prompt: str,
        model_class: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Generate + auto-parse into Pydantic v2 model"""
        response = await self.generate(prompt, system_prompt)
        if not model_class:
            raise ValueError("model_class must be provided")
        return safe_parse(model_class, response)

    def parse_json_list(self, response: str) -> List[dict[str, Any]]:
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
        return []

    async def close(self):
        """No-op for ChatPerplexity compatibility"""
        pass


async def test():
    """Test LLMService integration."""
    llm = LLMService()
    
    try:
        result = await llm.generate(
            "what is the latest news on NVDA", 
            "You are a debug agent testing my trading/news script. Confirm integration works."
        )
        print("✅ LLMService WORKS!")
        print(result)
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        await llm.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())