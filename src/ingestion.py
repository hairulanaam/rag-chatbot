import os
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
from pinecone import Pinecone
from src.config import PINECONE_API_KEY, PINECONE_INDEX_NAME
from src.document_chunker import DocumentChunker
from src.embeddings import get_embeddings

# Get all markdown files from the data directory
def get_markdown_files(data_dir: str) -> List[str]:
    data_path = Path(data_dir)
    md_files = list(data_path.glob("*.md"))
    print(f"📁 Found {len(md_files)} markdown files in {data_dir}")
    return [str(f) for f in md_files]

# Process all documents using DocumentChunker
def process_documents(file_paths: List[str], max_tokens: int = 450) -> List[Dict]:
    # Max tokens per chunk
    chunker = DocumentChunker(max_tokens=max_tokens)
    all_chunks = []
    
    for file_path in file_paths:
        try:
            chunks = chunker.process_documentation(file_path)
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
    
    print(f"📄 Total chunks from all documents: {len(all_chunks)}")
    return all_chunks

# Upload chunks to Pinecone vector store with content in metadata
def upload_to_pinecone(chunks: List[Dict], batch_size: int = 100):
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Check if index exists
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_indexes:
        raise ValueError(
            f"Index '{PINECONE_INDEX_NAME}' not found. "
            f"Available indexes: {existing_indexes}"
        )
    
    print(f"🔗 Connected to Pinecone index: {PINECONE_INDEX_NAME}")

    index = pc.Index(PINECONE_INDEX_NAME)
    embeddings_model = get_embeddings()
    texts = [chunk["content"] for chunk in chunks]
    print("⏳ Generating embeddings...")
    embeddings = embeddings_model.embed_documents(texts)
    
    # Prepare vectors with content in metadata
    print("📦 Preparing vectors for Pinecone...")
    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        vector = {
            'id': chunk['id'],
            'values': embedding,
            'metadata': {
                'content': chunk['content'], 
                'source': chunk['metadata']['source'],
                'section_title': chunk['metadata']['section_title'],
                'sequence': chunk['metadata']['sequence']
            }
        }
        vectors.append(vector)
    
    # Batch upload to Pinecone
    print(f"⏳ Uploading {len(vectors)} vectors to Pinecone...")
    for i in tqdm(range(0, len(vectors), batch_size), desc="Uploading batches"):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch)
    
    print(f"✅ Successfully uploaded {len(vectors)} vectors to Pinecone")
    print(f"   ├── Index: {PINECONE_INDEX_NAME}")
    print(f"   ├── Dimension: {embeddings_model.embedding_dim}")
    print(f"   └── Model: {embeddings_model.model_name}")
    
    return index

# Run the ingestion pipeline
def run_ingestion(data_dir: str = "data", max_tokens: int = 450):
    print("=" * 60)
    print("🚀 Starting Ingestion Pipeline")
    print("=" * 60)
    
    file_paths = get_markdown_files(data_dir)
    if not file_paths:
        print("No markdown files found. Exiting.")
        return
    
    chunks = process_documents(file_paths, max_tokens)
    if not chunks:
        print("No chunks created. Exiting.")
        return
    
    index = upload_to_pinecone(chunks)
    
    print("=" * 60)
    print("✅ Ingestion Pipeline Complete!")
    print("=" * 60)
    
    return index


if __name__ == "__main__":
    run_ingestion()
