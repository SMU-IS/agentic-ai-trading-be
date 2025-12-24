from typing import List

from pydantic import BaseModel, HttpUrl


class Ingestion(BaseModel):
    urls: List[HttpUrl]
