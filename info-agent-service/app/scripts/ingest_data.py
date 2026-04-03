import glob
import os

from langchain_core.documents import Document
from langchain_nomic import NomicEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.utils.logger import setup_logging

logger = setup_logging()


def get_embeddings():
    return NomicEmbeddings(
        model=settings.embedding_model,
        nomic_api_key=settings.nomic_api_key,
    )


def ingest():
    # 1. Initialize Client
    _ = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    # 2. Load Data
    documents = []
    knowledge_dir = "knowledge"
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)
        logger.info(
            f"Created {knowledge_dir} directory. Please put your .md or .txt files there."
        )
        return

    files = glob.glob(f"{knowledge_dir}/*.md") + glob.glob(f"{knowledge_dir}/*.txt")
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    documents.append(
                        Document(
                            page_content=content,
                            metadata={"source": os.path.basename(file_path)},
                        )
                    )
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")

    if not documents:
        logger.warning(
            "No documents found in 'knowledge/' to ingest. Put some .md or .txt files there first."
        )
        return

    # 3. Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_documents(documents)
    logger.info(f"Split {len(documents)} files into {len(chunks)} chunks.")

    # 4. Vectorize and Upload
    embeddings = get_embeddings()

    logger.info(
        f"Vectorizing and uploading to collection: {settings.qdrant_collection_name}..."
    )
    QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection_name,
        force_recreate=False,
    )
    logger.info("✅ Ingestion complete.")


if __name__ == "__main__":
    ingest()
