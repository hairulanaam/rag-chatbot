import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLAMA_PARSE_API_KEY = os.getenv("LLAMA_PARSE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_MODEL_NAME = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768

LLM_MODEL_NAME = "llama-3.3-70b-versatile"
SUGGESTION_MODEL_NAME = "llama-3.1-8b-instant"
STT_MODEL_NAME = "whisper-large-v3"

STT_PROMPT = (
    "Percakapan tentang informasi informasi SD Integral Luqman Al Hakim Situbondo dalam Bahasa Indonesia"
    "Konteks pembahasan: profil atau identitas sekolah, penerimaan Murid Baru (syarat dan alur pendaftaran), biaya Pendidikan (jenis dan ketentuan pembayaran), kurikulum operasional dan kebijakan operasional sekolah"
)

FALLBACK_PHRASES = [
    "mohon maaf",
    "informasi tersebut tidak tersedia",
    "tidak menemukan informasi",
    "di luar cakupan",
    "tidak ada informasi tentang",
    "tidak tersedia dalam konteks",
]

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "change-this-secret-key-in-production")
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
DATA_DIR = str(BASE_DIR / "data")