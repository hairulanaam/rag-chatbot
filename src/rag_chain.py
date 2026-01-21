from typing import List, Dict
from pinecone import Pinecone
from groq import Groq, RateLimitError as GroqRateLimitError
from langchain_core.documents import Document
from src.config import GROQ_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, LLM_MODEL_NAME
from src.embeddings import get_embeddings


# Custom exception for rate limit handling
class RateLimitError(Exception):
    """Raised when Groq API rate limit is exceeded (HTTP 429)"""
    def __init__(self, message: str, retry_after: int = None):
        self.message = message
        self.retry_after = retry_after  # seconds to wait before retry
        super().__init__(self.message)

SYSTEM_PROMPT = """
### System
Anda adalah admin virtual SD Integral Luqman Al Hakim Situbondo.

### Instructions
- Jawab HANYA berdasarkan konteks dokumen yang diberikan
- JANGAN mengarang informasi (terutama nama, angka, tanggal)
- Jika informasi tidak ditemukan: "Mohon maaf, informasi tidak tersedia. Silakan hubungi admin@sdintegralluqmanalhakim.sch.id atau kunjungi Jl. Gunung Bromo/Pasar Hewan Sumberkolak, Panarukan, Situbondo."
- Jika pertanyaan ambigu, minta klarifikasi
- Tolak sopan pertanyaan di luar konteks sekolah

### Output Format
- AWALAN: Sebutkan sumber dokumen singkat (contoh: "Berdasarkan Dokumen Profil Sekolah,..." atau "Berdasarkan Dokumen Kurikulum Operasional,...")
- ISI: Informasi lengkap dan akurat sesuai dokumen, gunakan poin-poin jika perlu
- PENUTUP (baris baru terpisah):
   - Jika informasi panjang/ada lanjutan: tawarkan "Apakah Anda membutuhkan informasi lebih lanjut mengenai [topik terkait]?"
   - Atau: "Silakan hubungi email admin@sdintegralluqmanalhakim.sch.id atau kunjungi sekolah di Jl. Gunung Bromo/Pasar Hewan Sumberkolak, Panarukan, Situbondo jika Anda memerlukan informasi lebih lanjut."
"""

# Format retrieved documents into context string
def format_docs(docs: List[Document]) -> str:
    formatted = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        section = doc.metadata.get("section_title", "")
        content = doc.page_content
        
        formatted.append(f"[Dokumen {i} - {source}: {section}]\n{content}")
    
    return "\n\n---\n\n".join(formatted)

# Format response for better display
def format_response(text: str) -> str:
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Format heading
        if line.strip().startswith('#'):
            formatted_lines.append(f"\n{line}\n")
        # Format list items
        elif line.strip().startswith(('-', '*', '•')):
            formatted_lines.append(line)
        # Format numbered list
        elif line.strip() and line.strip()[0].isdigit() and '.' in line[:3]:
            formatted_lines.append(line)
        else:
            formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)

class PineconeRetriever:
    # Custom retriever that uses E5 embeddings with query prefix.
    
    def __init__(self, k: int = 8):
        self.k = k
        self.embeddings = get_embeddings()
        
        pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index = pc.Index(PINECONE_INDEX_NAME)
        print(f"✅ Retriever initialized (k={k})")
    
    # Retrieve relevant documents for a query.
    def invoke(self, query: str) -> List[Document]:
        query_embedding = self.embeddings.embed_query(query)
        
        results = self.index.query(
            vector=query_embedding,
            top_k=self.k,
            include_metadata=True
        )
        
        # Convert Pinecone matches to LangChain Documents
        documents = []
        for match in results.matches:
            content = match.metadata.get("content", "")
            doc = Document(
                page_content=content,
                metadata={
                    "content": content,
                    "source": match.metadata.get("source", "Unknown"),
                    "section_title": match.metadata.get("section_title", ""),
                    "sequence": match.metadata.get("sequence", 0)
                }
            )
            documents.append(doc)
        
        return documents

# Groq LLM wrapper
class GroqLLM:
    def __init__(self, model_name: str = LLM_MODEL_NAME):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = model_name
        print(f"✅ LLM initialized: {model_name}")
    
    # Build user message with context and question.
    def _build_user_message(self, question: str, context: str) -> str:
        return f"""Konteks dari Dokumen Sekolah:
---
{context}
---

Pertanyaan: {question}"""

    # Generate answer based on question and context (non-streaming)
    def generate(self, question: str, context: str) -> str:
        try:
            user_message = self._build_user_message(question, context)

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                temperature=0.2,
                max_tokens=600,
                top_p=0.9,
                seed=700,
                stream=False
            )
            
            # Ekstrak token usage
            token_usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
            
            print(f"📊 Token Usage: Input={token_usage['prompt_tokens']}, Output={token_usage['completion_tokens']}, Total={token_usage['total_tokens']}")
        
            response_text = completion.choices[0].message.content
            return format_response(response_text.strip())
            
        except GroqRateLimitError as e:
            # Extract retry_after from error response if available
            retry_after = None
            if hasattr(e, 'response') and e.response is not None:
                retry_after = e.response.headers.get('retry-after')
                if retry_after:
                    retry_after = int(retry_after)
            
            print(f"⚠️ Rate limit exceeded. Retry after: {retry_after}s")
            raise RateLimitError(
                message="Mohon maaf, layanan sedang sibuk karena terlalu banyak permintaan. Silakan coba beberapa saat lagi.",
                retry_after=retry_after
            )
            
        except Exception as e:
            print(f"Groq API error: {str(e)}\")")
            raise
    
    # Generate answer with streaming 
    def generate_stream(self, question: str, context: str):
        try:
            user_message = self._build_user_message(question, context)

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                temperature=0.2,
                max_tokens=600,
                top_p=0.9,
                stream=True 
            )
            
            for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
                    
        except GroqRateLimitError as e:
            # Extract retry_after from error response if available
            retry_after = None
            if hasattr(e, 'response') and e.response is not None:
                retry_after = e.response.headers.get('retry-after')
                if retry_after:
                    retry_after = int(retry_after)
            
            print(f"⚠️ Rate limit exceeded. Retry after: {retry_after}s")
            raise RateLimitError(
                message="Mohon maaf, layanan sedang sibuk karena terlalu banyak permintaan. Silakan coba beberapa saat lagi.",
                retry_after=retry_after
            )
                    
        except Exception as e:
            print(f"Groq API error: {str(e)}")
            raise

# Initialize Pinecone retriever
def get_retriever(k: int = 4) -> PineconeRetriever:
    return PineconeRetriever(k=k)

# Initialize Groq LLM
def get_llm() -> GroqLLM:
    return GroqLLM()

class RAGChain:

    # Initialize RAG chain
    def __init__(self, k: int = 4):
        self.retriever = get_retriever(k=k)
        self.llm = get_llm()
        print("RAG chain created successfully")
    
    # Process a question through the RAG pipeline
    def invoke(self, question: str) -> Dict:
        # Retrieve relevant documents
        docs = self.retriever.invoke(question)
        
        # Check if we have results
        if not docs:
            return {
                "answer": ("Mohon maaf, saya tidak menemukan informasi yang relevan dengan pertanyaan Anda "
                          "dalam dokumen sekolah. Silakan coba dengan kata kunci lain atau hubungi "
                          "pihak sekolah secara langsung."),
                "sources": []
            }
        
        # Format context
        context = format_docs(docs)
        
        # Generate answer
        answer = self.llm.generate(question, context)
        
        return {
            "answer": answer,
            "sources": docs
        }

# Create RAG chain
def create_rag_chain(k: int = 4) -> RAGChain:
    return RAGChain(k=k)

# Create RAG chain components for Chainlit app
def create_rag_chain_with_sources(k: int = 4):
    retriever = get_retriever(k=k)
    llm = get_llm()
    return llm, retriever, format_docs
