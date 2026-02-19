import os
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLAMA_PARSE_API_KEY = os.getenv("LLAMA_PARSE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"
LLM_MODEL_NAME = "llama-3.3-70b-versatile"
SUGGESTION_MODEL_NAME = "llama-3.1-8b-instant"
STT_MODEL_NAME = "whisper-large-v3-turbo"