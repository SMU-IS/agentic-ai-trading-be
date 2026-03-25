from enum import Enum


class APIPath(str, Enum):
    PREPROCESS = "/preprocess"
    ANALYSE = "/analysis"


class LLMProviders(str, Enum):
    OLLAMA = "ollama"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
    QDRANT_GEMINI = "qdrant_gemini"


DEFAULT_RULES = {
    "earnings": [
        r"earnings release",
        r"quarterly results",
        r"EPS",
        r"revenue report",
    ],
    "merger_acquisition": [
        r"merger",
        r"acquisition",
        r"acquire",
        r"buyout",
        r"takeover",
    ],
    "regulatory": [r"FDA approval", r"antitrust", r"lawsuit", r"sanction", r"fine"],
    "macro": [r"interest rate", r"inflation", r"CPI", r"fed hike", r"cut rates"],
    "product": [r"product launch", r"unveil", r"announced new"],
}
