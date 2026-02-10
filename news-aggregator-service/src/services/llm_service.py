import httpx
import json
import re
import os
from typing import List
from pydantic import BaseModel
from src.services.json_parser import safe_parse

class LLMService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("PPLX_API_KEY")
        if not self.api_key:
            raise ValueError("PPLX_API_KEY not set")
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def generate(self, prompt: str, system_prompt: str = None, model: str = "sonar") -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
            
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": False
        }
        
        try:
            response = await self.client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            print(f"❌ API Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            raise
    
    async def generate_list(self, prompt: str) -> List[dict]:
        response = await self.generate(prompt)
        return self.parse_json_list(response)
    
    async def generate_parse_json(self, prompt: str,  system_prompt: str = None, model_class: type[BaseModel] = None) -> BaseModel:
        """Generate + auto-parse into Pydantic model"""
        response = await self.generate(prompt, system_prompt)
        return safe_parse(model_class, response)

    
    def parse_json_list(self, response: str) -> List[dict]:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        return []
    
    async def close(self):
        await self.client.aclose()