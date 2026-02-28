from typing import List, Dict
from pinecone import Pinecone
from groq import Groq, RateLimitError as GroqRateLimitError
from langchain_core.documents import Document
from src.config import GROQ_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, LLM_MODEL_NAME, SUGGESTION_MODEL_NAME
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
- Jika informasi tidak ditemukan: "Mohon maaf, informasi tidak tersedia. Silakan hubungi admin@sdintegralluqmanalhakim.sch.id atau kunjungi alamat sekolah di Jl. Gunung Bromo/Pasar Hewan Sumberkolak, Panarukan, Situbondo."
- Jika pertanyaan ambigu, minta klarifikasi
- Tolak sopan pertanyaan di luar konteks sekolah

### Output Format
- AWALAN: Sebutkan sumber dokumen singkat (contoh: "Berdasarkan Dokumen Profil Sekolah,..." atau "Berdasarkan Dokumen Kurikulum Operasional,...")
- ISI: Informasi lengkap dan akurat sesuai dokumen, gunakan poin-poin jika perlu
"""

# --- Suggestion Prompt (separated into system/user roles) ---

SUGGESTION_SYSTEM_PROMPT = """### System
Anda adalah AI pembuat saran pertanyaan lanjutan untuk chatbot layanan informasi SD Integral Luqman Al Hakim Situbondo. Tugas Anda adalah memberikan maksimal 2 ide pertanyaan lanjutan yang relevan.

### Instructions
1. Pertanyaan HARUS bisa dijawab oleh informasi yang ADA di bagian "Konteks dokumen".
2. DILARANG membuat pertanyaan yang jawabannya TIDAK ADA di konteks dokumen atau jika konteks kosong.
3. DILARANG membuat pertanyaan yang jawabannya SUDAH TERCAKUP di bagian "Jawaban yang diberikan". Pastikan saran Anda menanyakan detail yang BERBEDA.
4. JANGAN MENEBAK, PERIKSA KEMBALI apakah jawabannya benar-benar tertulis di konteks. Jika tidak tertulis, BUANG pertanyaan tersebut.
5. Pertanyaan harus singkat, padat, dan jelas (maksimal 10 kata per pertanyaan).
6. Format keluaran HANYA berupa teks pertanyaan, satu per baris, tanpa nomor, tanpa bullet, tanpa tanda kutip.
7. Jika SEMUA informasi di konteks sudah habis dibahas di jawaban, atau jika tidak ada saran yang valid, Anda WAJIB mengeluarkan teks: TIDAK_ADA

### Expected Output Format
[Pertanyaan 1]
[Pertanyaan 2]
###

### Contoh 1
Konteks dokumen: "Syarat masuk: usia minimal 6 tahun, fotocopy akta kelahiran, pas foto 3x4. Biaya pendaftaran Rp200.000."
Pertanyaan user: Bagaimana proses pendaftaran murid baru?
Jawaban yang diberikan: Proses pendaftaran terdiri dari: membayar uang pendaftaran, mengisi formulir, observasi, pengumuman, dan daftar ulang.
Saran pertanyaan:
Apa saja syarat pendaftaran murid baru?
Berapa biaya pendaftaran murid baru?
###

### Contoh 2
Konteks dokumen: "Infaq Pembangunan, Sarana Prasarana, Seragam, Kegiatan, Buku, SPP, Tabungan Rihlah"
Pertanyaan user: Apa saja jenis pembayaran sekolah?
Jawaban yang diberikan: Jenis pembayaran sekolah adalah Infaq Pembangunan, Sarana Prasarana, Seragam, Kegiatan, Buku, SPP, Tabungan Rihlah
Saran pertanyaan:
Apa kontak bendahara sekolah?
Bagaimana ketentuan pembayaran biaya sekolah?
###

### Contoh 3 (PENTING: Jangan menanyakan informasi yang tidak ada di konteks)
Konteks dokumen: "Ekstrakurikuler wajib di SD Integral Luqman Al Hakim adalah Pramuka. Selain itu ada pilihan Panahan dan Robotik."
Pertanyaan user: Apa saja ekstrakurikuler di sekolah?
Jawaban yang diberikan: Ekstrakurikuler wajib adalah Pramuka, sedangkan pilihan lainnya adalah Panahan dan Robotik.
Saran pertanyaan:
TIDAK_ADA 
"""

SUGGESTION_USER_PROMPT = """Konteks dokumen:
{context}

Pertanyaan user: {question}
Jawaban yang diberikan: {answer}

Saran pertanyaan:"""

# Format retrieved documents into context string
def format_docs(docs: List[Document]) -> str:
    formatted = []
    for doc in docs:
        source = doc.metadata.get("source", "Unknown")
        section = doc.metadata.get("section_title", "")
        content = doc.page_content
        
        formatted.append(f"[{source}: {section}]\n{content}")
    
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

# School name patterns to remove from query (sorted by length, longest first)
SCHOOL_NAME_PATTERNS = [
    "sd integral luqman al hakim situbondo",
    "sd integral luqman al hakim",
    "sd luqman al hakim situbondo",
    "sd luqman al hakim",
    "luqman al hakim situbondo",
    "luqman al hakim",
    "sd integral",
]

def rewrite_query(query: str) -> str:
    """
    Rewrite query untuk optimasi retrieval.
    - Hapus nama sekolah (redundant karena semua dokumen tentang sekolah ini)
    - Normalisasi whitespace
    """
    rewritten = query.lower()
    
    # Hapus nama sekolah dari query
    for pattern in SCHOOL_NAME_PATTERNS:
        rewritten = rewritten.replace(pattern, "")
    
    # Normalisasi whitespace
    rewritten = " ".join(rewritten.split())
    
    # Jika query kosong setelah rewrite, gunakan query asli
    if not rewritten.strip():
        return query
    
    return rewritten


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
        # Rewrite query untuk optimasi retrieval
        rewritten_query = rewrite_query(query)
        
        query_embedding = self.embeddings.embed_query(rewritten_query)
        
        results = self.index.query(
            vector=query_embedding,
            top_k=self.k,
            include_metadata=True
        )
        
        # DEBUG: Log query results
        print(f"\n📝 Original Query: '{query}'")
        print(f"🔄 Rewritten Query: '{rewritten_query}'")
        print(f"📊 Pinecone returned {len(results.matches)} matches")
        for i, match in enumerate(results.matches):  # Show ALL matches
            print(f"   [{i+1}] Score: {match.score:.4f} | Section: {match.metadata.get('section_title', 'N/A')}")
        
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
                    "sequence": match.metadata.get("sequence", 0),
                    "score": match.score  # Store similarity score for downstream filtering
                }
            )
            documents.append(doc)
        
        print(f"📄 Returning {len(documents)} documents to RAG chain\n")
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
                # top_p=0.9,
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
                # top_p=0.9,
                seed=700,
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
    
    # Generate context-aware query suggestions using lightweight model
    def generate_suggestions(self, question: str, docs: List[Document], answer: str) -> List[str]:
        try:
            # Filter docs by relative score threshold (95% of top score)
            if docs:
                top_score = max(doc.metadata.get("score", 0) for doc in docs)
                threshold = top_score * 0.85
                relevant_docs = [doc for doc in docs if doc.metadata.get("score", 0) >= threshold]
                
                print(f"🔍 Suggestion filter: top_score={top_score:.4f}, threshold={threshold:.4f}, {len(relevant_docs)}/{len(docs)} docs passed")
            else:
                relevant_docs = []
            
            if not relevant_docs:
                return []
            
            # Build context from filtered docs only
            filtered_context = format_docs(relevant_docs)
            
            user_prompt = SUGGESTION_USER_PROMPT.format(
                context=filtered_context[:2000],
                question=question,
                answer=answer[:1500]
            )
            
            completion = self.client.chat.completions.create(
                model=SUGGESTION_MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": SUGGESTION_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                temperature=0.0,
                max_tokens=100,
                # top_p=0.9,
                stop=["###"],
                stream=False
            )
            
            response_text = completion.choices[0].message.content.strip()
            
            # Handle "no relevant suggestions" response
            if "TIDAK_ADA" in response_text.upper():
                print("💡 No relevant suggestions for this topic")
                return []
            
            # Parse suggestions: split by newline, clean up
            suggestions = []
            print(f"📨 Raw suggestion response: {repr(response_text)}")
            for line in response_text.split("\n"):
                line = line.strip()
                # Remove numbering/bullets if model adds them
                line = line.lstrip("0123456789.-) ").strip()
                # Only accept valid question lines (must end with ?)
                if (line and len(line) > 5 and len(line) <= 80 
                    and line.endswith("?")
                    and "TIDAK_ADA" not in line.upper()):
                    suggestions.append(line)
            
            # Return max 2 suggestions
            suggestions = suggestions[:2]
            
            print(f"💡 Generated {len(suggestions)} suggestions")
            for i, s in enumerate(suggestions, 1):
                print(f"   [{i}] {s}")
            
            return suggestions
            
        except Exception as e:
            print(f"⚠️ Suggestion generation failed (non-critical): {str(e)}")
            return []

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
