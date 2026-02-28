import time
from typing import List
from google import genai
from src.config import GOOGLE_API_KEY, EMBEDDING_MODEL_NAME, EMBEDDING_DIMENSION


class Embeddings:    
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, output_dimensionality: int = EMBEDDING_DIMENSION):
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY tidak ditemukan di environment variables!")
        
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        self.model_name = model_name
        self.embedding_dim = output_dimensionality
        self.output_dimensionality = output_dimensionality
        
        # Warm-up & validasi koneksi
        try:
            test_result = self.client.models.embed_content(
                model=self.model_name,
                contents="warmup test",
                config={
                    "task_type": "RETRIEVAL_QUERY",
                    "output_dimensionality": self.output_dimensionality
                }
            )
            actual_dim = len(test_result.embeddings[0].values)
            self.embedding_dim = actual_dim
            print(f"✅ Loaded embedding model: {model_name} (dim: {actual_dim})")
        except Exception as e:
            raise ConnectionError(f"❌ Gagal connect ke Google Embedding API: {e}")
    
    def _embed_with_retry(self, contents, task_type: str, max_retries: int = 3):
        """Helper: embed dengan retry dan exponential backoff."""
        for attempt in range(max_retries):
            try:
                return self.client.models.embed_content(
                    model=self.model_name,
                    contents=contents,
                    config={
                        "task_type": task_type,
                        "output_dimensionality": self.output_dimensionality
                    }
                )
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  ⏳ Retry {attempt + 1}/{max_retries} dalam {wait_time}s... ({e})")
                    time.sleep(wait_time)
                else:
                    raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed dokumen untuk indexing ke Pinecone.
        task_type=RETRIEVAL_DOCUMENT — dioptimasi agar dokumen mudah ditemukan.
        """
        batch_size = 100  # Batas Google API per request
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                result = self._embed_with_retry(batch, task_type="RETRIEVAL_DOCUMENT")
                batch_embeddings = [list(e.values) for e in result.embeddings]
                all_embeddings.extend(batch_embeddings)
                print(f"  📦 Embedded batch {i // batch_size + 1}/{-(-len(texts) // batch_size)} ({len(batch)} texts)")
            except Exception as e:
                print(f"  ❌ Error embedding batch {i // batch_size + 1}: {e}")
                raise
        
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed query user untuk pencarian di Pinecone.
        task_type=RETRIEVAL_QUERY — dioptimasi untuk menemukan dokumen relevan.
        
        Dipilih daripada QUESTION_ANSWERING karena:
        - User chatbot tidak selalu mengirim proper question
        - Bisa berupa keyword, frasa, atau perintah
        - RETRIEVAL_QUERY menangani semua jenis input dengan baik
        """
        try:
            result = self._embed_with_retry(text, task_type="RETRIEVAL_QUERY")
            return list(result.embeddings[0].values)
        except Exception as e:
            print(f"❌ Error embedding query: {e}")
            raise


def get_embeddings() -> Embeddings:
    """Factory function untuk membuat instance Embeddings"""
    return Embeddings(
        model_name=EMBEDDING_MODEL_NAME,
        output_dimensionality=EMBEDDING_DIMENSION
    )
