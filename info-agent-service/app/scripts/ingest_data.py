import glob
import os
import uuid

from langchain_core.documents import Document
from langchain_nomic import NomicEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient

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
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    # 2. Load Data
    knowledge_dir = "knowledge"
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)
        logger.info(f"Created {knowledge_dir} directory.")
        return

    files = glob.glob(f"{knowledge_dir}/*.md") + glob.glob(f"{knowledge_dir}/*.txt")

    # 3. Process files and check for existing point_ids
    embeddings = get_embeddings()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

    for file_path in files:
        file_name = os.path.basename(file_path)
        # Use filename as a deterministic namespace for UUIDs
        file_uuid_namespace = uuid.uuid5(uuid.NAMESPACE_DNS, file_name)

        # Check if the first chunk of this file already exists
        first_chunk_id = str(uuid.uuid5(file_uuid_namespace, "chunk_0"))
        try:
            existing = client.retrieve(
                collection_name=settings.qdrant_collection_name, ids=[first_chunk_id]
            )
            if existing:
                logger.info(f"Skipping {file_name}: already exists in Qdrant.")
                continue
        except Exception:
            # Collection might not exist yet
            pass

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    continue

                doc = Document(page_content=content, metadata={"source": file_name})
                chunks = text_splitter.split_documents([doc])

                # Generate deterministic IDs for all chunks
                ids = [
                    str(uuid.uuid5(file_uuid_namespace, f"chunk_{i}"))
                    for i in range(len(chunks))
                ]

                logger.info(f"Ingesting {file_name} ({len(chunks)} chunks)...")
                QdrantVectorStore.from_documents(
                    chunks,
                    embeddings,
                    ids=ids,
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key,
                    collection_name=settings.qdrant_collection_name,
                )
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    logger.info("✅ Ingestion check complete.")


if __name__ == "__main__":
    ingest()
