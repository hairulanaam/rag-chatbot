import os
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
from pinecone import Pinecone
from src.config import PINECONE_API_KEY, PINECONE_INDEX_NAME
from src.document_chunker import DocumentChunker
from src.embeddings import get_embeddings

def get_markdown_files(data_dir: str) -> List[str]:
    data_path = Path(data_dir)
    md_files = list(data_path.glob("*.md"))
    print(f"📁 Found {len(md_files)} markdown files in {data_dir}")
    return [str(f) for f in md_files]

def process_documents(file_paths: List[str], max_tokens: int = 1840) -> List[Dict]:
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

def upload_to_pinecone(chunks: List[Dict], batch_size: int = 100):
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_indexes:
        raise ValueError(
            f"Index '{PINECONE_INDEX_NAME}' not found. "
            f"Available indexes: {existing_indexes}"
        )

    index = pc.Index(PINECONE_INDEX_NAME)
    embeddings_model = get_embeddings()
    texts = [chunk["content"] for chunk in chunks]
    embeddings = embeddings_model.embed_documents(texts)
    
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
    
    print(f"⏳ Uploading {len(vectors)} vectors to Pinecone...")
    for i in tqdm(range(0, len(vectors), batch_size), desc="Uploading batches"):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch)
    
    print(f"✅ Successfully uploaded {len(vectors)} vectors to Pinecone")
    print(f"   ├── Index: {PINECONE_INDEX_NAME}")
    print(f"   ├── Dimension: {embeddings_model.embedding_dim}")
    print(f"   └── Model: {embeddings_model.model_name}")
    
    return index

def run_ingestion(data_dir: str = "data", max_tokens: int = 1840):
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
# Per-document operations
# ============================================================

def _get_pinecone_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)


def delete_document_vectors(file_prefix: str) -> dict:
    index = _get_pinecone_index()
    
    prefix = f"{file_prefix}_section_"
    deleted_count = 0
    
    try:
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


def index_single_document(file_path: str, max_tokens: int = 1840) -> dict:
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        chunker = DocumentChunker(max_tokens=max_tokens)
        chunks = chunker.process_documentation(file_path)
        
        if not chunks:
            return {"success": False, "error": "No chunks created from document"}
        
        upload_to_pinecone(chunks)
        
        return {
            "success": True, 
            "chunks_count": len(chunks),
            "file": path.name
        }
        
    except Exception as e:
        print(f"❌ Error indexing document: {e}")
        return {"success": False, "error": str(e)}


def reindex_document(file_path: str, max_tokens: int = 1840) -> dict:
    path = Path(file_path)
    file_prefix = path.stem
    
    delete_result = delete_document_vectors(file_prefix)
    index_result = index_single_document(file_path, max_tokens)
    
    return {
        "success": index_result.get("success", False),
        "deleted_count": delete_result.get("deleted_count", 0),
        "chunks_count": index_result.get("chunks_count", 0),
        "file": path.name,
        "error": index_result.get("error") or delete_result.get("error")
    }


def get_index_stats() -> dict:
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


def check_documents_indexed(file_stems: list) -> dict:
    try:
        index = _get_pinecone_index()
        result = {}
        for stem in file_stems:
            prefix = f"{stem}_section_"
            has_vectors = False
            for ids in index.list(prefix=prefix):
                if ids:
                    has_vectors = True
                    break
            result[stem] = has_vectors
        return {"success": True, "indexed": result}
    except Exception as e:
        print(f"❌ Error checking index status: {e}")
        return {"success": False, "indexed": {stem: None for stem in file_stems}}

if __name__ == "__main__":
    run_ingestion()
