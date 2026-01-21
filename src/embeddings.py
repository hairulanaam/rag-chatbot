from typing import List
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL_NAME

class Embeddings:
    # Initialize the Embeddings with default model name
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"✅ Loaded embedding model: {model_name} (dim: {self.embedding_dim})")
    
    def get_embeddings():
        ...
        embeddings = E5Embedding(model)
        
        # Pre-warm the model
        print("🔥 Warming up embedding model...")
        _ = embeddings.embed_query("test query")
        print("✅ Model ready!")
        
        return embeddings

    # Embed documents with 'passage:' prefix
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        prefixed_texts = [f"passage: {text}" for text in texts]
        
        embeddings = self.model.encode(
            prefixed_texts,
            show_progress_bar=True,
            batch_size=32,
            normalize_embeddings=True
        )
        
        return embeddings.tolist()
    
    # Embed query with 'query:' prefix
    def embed_query(self, text: str) -> List[float]:
        prefixed_text = f"query: {text}"
        
        embedding = self.model.encode(
            prefixed_text,
            normalize_embeddings=True
        )
        
        return embedding.tolist()


def get_embeddings() -> Embeddings:
    return Embeddings(model_name=EMBEDDING_MODEL_NAME)
