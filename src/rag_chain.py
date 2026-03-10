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
Anda adalah admin virtual SD Integral Luqman Al Hakim Situbondo. Tugas Anda adalah memberikan informasi sekolah secara lengkap dan tuntas kepada pengguna.

### Instructions
- Jawab HANYA berdasarkan konteks dokumen yang diberikan
- DILARANG menyuruh pengguna untuk merujuk ke dokumen, brosur, lampiran, atau sumber eksternal yang TIDAK tersedia dalam konteks percakapan ini. Anda harus menyampaikan isi informasinya secara langsung.
- DILARANG mengarang informasi (terutama nama, angka, tanggal, kontak)
- Jika pertanyaan ambigu, minta klarifikasi
- Tolak sopan pertanyaan di luar konteks sekolah
- Jika informasi tidak ditemukan dalam dokumen yang tersedia, gunakan respons fallback di bawah

### Fallback (jika informasi tidak tersedia)
Gunakan PERSIS kalimat ini:
"Mohon maaf, informasi tersebut tidak tersedia dalam sistem kami saat ini. 
Silakan hubungi kami langsung melalui:
- Email: admin@sdintegralluqmanalhakim.sch.id
- Kunjungi: Jl. Gunung Bromo/Pasar Hewan Sumberkolak, Panarukan, Situbondo"

### Output Format
- AWALAN: Sebutkan sumber dokumen singkat (contoh: "Berdasarkan Dokumen Profil Sekolah,..." atau "Berdasarkan Dokumen Kurikulum Operasional,...")
- ISI: Informasi lengkap dan akurat sesuai dokumen, gunakan poin-poin jika perlu
"""

# --- Suggestion Prompt (separated into system/user roles) ---

SUGGESTION_SYSTEM_PROMPT = """### System
Anda adalah AI pembuat saran pertanyaan lanjutan untuk chatbot SD Integral Luqman Al Hakim Situbondo. Tugas Anda adalah mengubah judul topik dari daftar "Topik tersedia" menjadi kalimat tanya yang belum dibahas

### Rules
1. Anda HANYA boleh memilih topik dari daftar "Topik tersedia"
2. Ubah judul topik/section menjadi kalimat tanya langsung (Contoh: judul "Dokumen Pendaftaran" → pertanyaan "Apa saja dokumen pendaftaran?"). DILARANG menambahkan istilah atau ide yang tidak ada di judul topik.
3. DILARANG membuat pertanyaan yang isinya sama atau mirip dengan "Pertanyaan user", meskipun judulnya berbeda.
4. Gunakan "Jawaban yang diberikan" HANYA untuk mendeteksi apakah isi sebuah topik sudah dibahas. JANGAN gunakan kosakata dari jawaban sebagai bahan pertanyaan baru.
5. Pertanyaan harus umum, formal, dan maksimal 10 kata per pertanyaan.
6. Format: teks langsung, satu per baris, tanpa nomor/bullet/tanda kutip.
7. Keluarkan TIDAK_ADA jika:
   - Semua topik sudah dibahas habis di jawaban, ATAU
   - Judul semua topik yang tersisa sudah terwakili oleh pertanyaan user

### Contoh 1 (judul topik belum dibahas maka buat saran pertanyaan yang berbeda dari pertanyaan user)
Topik tersedia:
- Topik: Tahapan Pendaftaran murid baru (dari sumber dokumen: Kebijakan Penerimaan Murid Baru)
- Topik: Dokumen Pendaftaran (dari sumber dokumen: Kebijakan Penerimaan Murid Baru)
- Topik: Jadwal Pendaftaran dan Kontak (dari sumber dokumen: Brosur Sistem Penerimaan Murid Baru)
Pertanyaan user: Bagaimana proses pendaftaran siswa baru?
Jawaban yang diberikan: Proses pendaftaran siswa baru di SD Integral Luqman Al-Hakim Situbondo adalah sebagai berikut: Pembayaran Biaya Pendaftaran:...
Saran pertanyaan:
Apa saja dokumen yang diperlukan untuk pendaftaran?
Kapan jadwal pendaftaran siswa baru?
###

### Contoh 2 (judul topik sudah terwakili pertanyaan user maka abaikan, pilih topik lain)
Topik tersedia:
- Topik: Dokumen Pendaftaran (dari: Kebijakan PMB)
- Topik: Tahapan Pendaftaran murid baru (dari: Kebijakan PMB)
Pertanyaan user: Apa saja dokumen yang dibutuhkan untuk pendaftaran?
Jawaban yang diberikan: Dokumen yang diperlukan adalah KK, Akta Kelahiran, 
dan pas foto 3x4.
Saran pertanyaan:
Bagaimana tahapan pendaftaran murid baru?
###
"""

SUGGESTION_USER_PROMPT = """Topik tersedia:
{sections}

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
    
    def __init__(self, k: int = 4):
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
                max_tokens=1000,
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
    
    # Generate topic-based query suggestions from section headings
    def generate_suggestions(self, question: str, docs: List[Document], answer: str) -> List[str]:
        try:
            if not docs:
                return []
            
            # Extract unique section titles with source from retrieved docs
            seen = set()
            available_sections = []
            for doc in docs:
                section = doc.metadata.get("section_title", "").strip()
                source = doc.metadata.get("source", "").strip()
                key = f"{source}|{section}"
                if section and key not in seen:
                    seen.add(key)
                    available_sections.append(f"- Topik: {section} (dari sumber dokumen: {source})")
            
            if not available_sections:
                return []
            
            sections_text = "\n".join(available_sections)
            print(f"🔍 Suggestion sections: {len(available_sections)} topics from {len(docs)} docs")
            for s in available_sections:
                print(f"   {s}")
            
            user_prompt = SUGGESTION_USER_PROMPT.format(
                sections=sections_text,
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
                max_tokens=200,
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
                if (line and len(line) > 3 and len(line) <= 80 
                    # and line.endswith("?")
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
