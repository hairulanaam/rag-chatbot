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


# ============================================================
# Per-document operations for Dashboard
# ============================================================

def _get_pinecone_index():
    """Get Pinecone index instance."""
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)


def delete_document_vectors(file_prefix: str) -> dict:
    """
    Delete all vectors from Pinecone associated with a specific document.
    Vectors are identified by ID prefix (e.g., 'profil_section_*').
    
    Returns dict with deletion results.
    """
    index = _get_pinecone_index()
    
    # List all vector IDs with the file prefix
    prefix = f"{file_prefix}_section_"
    deleted_count = 0
    
    try:
        # Use list to find all vector IDs with prefix
        results = index.list(prefix=prefix)
        all_ids = []
        
        for ids in results:
            all_ids.extend(ids)
        
        if all_ids:
            # Delete in batches of 100
            for i in range(0, len(all_ids), 100):
                batch = all_ids[i:i + 100]
                index.delete(ids=batch)
                deleted_count += len(batch)
        
        print(f"🗑️ Deleted {deleted_count} vectors with prefix '{prefix}'")
        return {"success": True, "deleted_count": deleted_count, "prefix": prefix}
        
    except Exception as e:
        print(f"❌ Error deleting vectors: {e}")
        return {"success": False, "error": str(e), "deleted_count": 0}


def index_single_document(file_path: str, max_tokens: int = 450) -> dict:
    """
    Index a single document to Pinecone.
    
    Returns dict with indexing results.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        # Chunk the document
        chunker = DocumentChunker(max_tokens=max_tokens)
        chunks = chunker.process_documentation(file_path)
        
        if not chunks:
            return {"success": False, "error": "No chunks created from document"}
        
        # Upload to Pinecone
        upload_to_pinecone(chunks)
        
        return {
            "success": True, 
            "chunks_count": len(chunks),
            "file": path.name
        }
        
    except Exception as e:
        print(f"❌ Error indexing document: {e}")
        return {"success": False, "error": str(e)}


def reindex_document(file_path: str, max_tokens: int = 450) -> dict:
    """
    Re-index a document: delete old vectors then index fresh.
    
    Returns dict with re-indexing results.
    """
    path = Path(file_path)
    file_prefix = path.stem
    
    # Step 1: Delete old vectors
    delete_result = delete_document_vectors(file_prefix)
    
    # Step 2: Index the document fresh
    index_result = index_single_document(file_path, max_tokens)
    
    return {
        "success": index_result.get("success", False),
        "deleted_count": delete_result.get("deleted_count", 0),
        "chunks_count": index_result.get("chunks_count", 0),
        "file": path.name,
        "error": index_result.get("error") or delete_result.get("error")
    }


def get_index_stats() -> dict:
    """
    Get Pinecone index statistics.
    
    Returns dict with index stats.
    """
    try:
        index = _get_pinecone_index()
        stats = index.describe_index_stats()
        
        return {
            "success": True,
            "total_vector_count": stats.total_vector_count,
            "dimension": stats.dimension,
            "index_name": PINECONE_INDEX_NAME,
            "namespaces": {
                ns: {"vector_count": data.vector_count}
                for ns, data in stats.namespaces.items()
            } if stats.namespaces else {}
        }
    except Exception as e:
        print(f"❌ Error getting index stats: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    run_ingestion()
