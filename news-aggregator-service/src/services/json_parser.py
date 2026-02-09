from typing import Any, Dict, List, Union
from pydantic import BaseModel
import json
import re

def extract_json_from_response(response: str) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
    """
    Extract JSON from LLM response (handles markdown, explanations, partial JSON)
    Returns: dict, list, or None
    """
    # Remove markdown code blocks
    response = re.sub(r'```json\s*|\s*```', '', response)
    response = re.sub(r'```[\w]*\s*|\s*```', '', response)
    
    # Try common JSON patterns
    patterns = [
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Single object
        r'\[(?:\{[^{}]*\}[^{}]*)*\]',        # Array of objects
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            for match in matches:
                try:
                    parsed = json.loads(match)
                    return parsed
                except json.JSONDecodeError:
                    continue
    
    # Fallback: entire response
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        return None

def safe_parse(model_class: type[BaseModel], json_str: str):
    """
    Safely parse JSON string into Pydantic model
    Returns model instance or raises ValueError with details
    """
    json_data = extract_json_from_response(json_str)
    if not json_data:
        raise ValueError(f"No valid JSON found in response: {json_str[:200]}...")
    
    try:
        return model_class.model_validate(json_data)
    except Exception as e:
        raise ValueError(f"Pydantic validation failed: {str(e)}\nRaw data: {json_data}")