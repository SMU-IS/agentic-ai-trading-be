import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """
    This fixture runs once per session and injects dummy
    variables using square brackets [] so Pydantic doesn't crash.
    """

    # LLM Settings
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["LARGE_LANGUAGE_MODEL"] = "mock-model"
    os.environ["MAX_COMPLETION_TOKEN"] = "100"
    os.environ["TEMPERATURE"] = "0.5"
    os.environ["GROQ_API_KEY"] = "mock-key"

    # API / Retrieval URLs
    os.environ["QDRANT_RETRIEVAL_QUERY_URL"] = "http://mock"
    os.environ["ORDER_DETAILS_QUERY_URL"] = "http://mock"

    # AWS Settings
    os.environ["AWS_ACCESS_KEY_ID"] = "mock"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "mock"
    os.environ["AWS_S3_BUCKET_NAME"] = "mock"
    os.environ["AWS_S3_FILE_NAME"] = "mock"

    # Database Settings
    os.environ["POSTGRES_USER"] = "mock"
    os.environ["POSTGRES_PASSWORD"] = "mock"
    os.environ["POSTGRES_DB"] = "mock"

    # Redis Settings
    os.environ["REDIS_HOST"] = "mock"
    os.environ["REDIS_PORT"] = "6379"
    os.environ["REDIS_PASSWORD"] = "mock"
