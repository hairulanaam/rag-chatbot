import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLAMA_PARSE_API_KEY = os.getenv("LLAMA_PARSE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

# Embedding - Google Gemini Embedding (API)
EMBEDDING_MODEL_NAME = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768  # Diturunkan dari 3072 default untuk efisiensi storage Pinecone

LLM_MODEL_NAME = "llama-3.3-70b-versatile"
SUGGESTION_MODEL_NAME = "llama-3.1-8b-instant"
STT_MODEL_NAME = "whisper-large-v3-turbo"

# Dashboard Configuration
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "change-this-secret-key-in-production")
DATABASE_PATH = str(BASE_DIR / "dashboard.db")
DATA_DIR = str(BASE_DIR / "data")