import chainlit as cl
import numpy as np
import time
from src.rag_chain import PineconeRetriever, GroqLLM, format_docs, RateLimitError
from src.database import log_query
from src.audio_handler import AudioHandler, SILENCE_THRESHOLD, SILENCE_TIMEOUT, MIN_AUDIO_DURATION
from src.config import FALLBACK_PHRASES

# Configuration
USE_STREAMING = True  # Set False untuk non-streaming mode


# Starters - Quick question buttons for better UX
@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="📝 Bagaimana proses pendaftaran siswa baru?",
            message="Bagaimana proses pendaftaran siswa baru?",
        ),
        cl.Starter(
            label="💬 Bagaimana cara menghubungi sekolah?",
            message="Bagaimana cara menghubungi sekolah?",
        ),
    ]

# Initialize the chat session
@cl.on_chat_start
async def on_chat_start():
    # Welcome message dipindahkan ke chainlit.md agar Starters tetap tampil
    # Tidak perlu mengirim message di sini
    
    # Initialize components
    try:
        retriever = PineconeRetriever(k=4)
        llm = GroqLLM()
        audio_handler = AudioHandler()
        
        cl.user_session.set("retriever", retriever)
        cl.user_session.set("llm", llm)
        cl.user_session.set("audio_handler", audio_handler)
        
        print("Chat session initialized with streaming and audio support")
        
    except Exception as e:
        await cl.Message(
            content=f"Terjadi kesalahan saat inisialisasi: {str(e)}"
        ).send()


# Action callback - when user clicks a suggestion button
@cl.action_callback("suggestion")
async def on_suggestion(action: cl.Action):
    """Handle suggestion button click - send as new question"""
    suggestion_query = action.payload["query"]
    
    # Show user's selected suggestion as their message
    await cl.Message(
        author="You",
        type="user_message",
        content=suggestion_query,
    ).send()
    
    # Process the suggestion through RAG pipeline
    await process_question(suggestion_query)


# Audio Handling
@cl.on_audio_start
async def on_audio_start():
    """Initialize audio recording session"""
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("silent_duration_ms", 0)
    cl.user_session.set("is_speaking", False)
    cl.user_session.set("last_elapsed_time", 0)
    cl.user_session.set("audio_auto_ended", False)
    print("🎤 Audio recording started")
    return True


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    """Process incoming audio chunks with silence detection"""
    # Skip if already auto-ended by silence detection
    if cl.user_session.get("audio_auto_ended"):
        return
    
    audio_chunks = cl.user_session.get("audio_chunks")
    
    # Convert chunk data to numpy array (used for both storage and energy calculation)
    audio_chunk = np.frombuffer(chunk.data, dtype=np.int16)
    
    if audio_chunks is not None:
        audio_chunks.append(audio_chunk)
    
    # If this is the first chunk, initialize timers
    if chunk.isStart:
        cl.user_session.set("last_elapsed_time", chunk.elapsedTime)
        cl.user_session.set("is_speaking", True)
        return
    
    # Get session state
    last_elapsed_time = cl.user_session.get("last_elapsed_time")
    silent_duration_ms = cl.user_session.get("silent_duration_ms")
    is_speaking = cl.user_session.get("is_speaking")
    
    # Calculate time difference
    time_diff_ms = chunk.elapsedTime - last_elapsed_time
    cl.user_session.set("last_elapsed_time", chunk.elapsedTime)
    
    # Compute audio energy (RMS) using NumPy — replaces deprecated audioop
    audio_energy = int(np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2)))
    
    if audio_energy < SILENCE_THRESHOLD:
        # Audio is silent
        silent_duration_ms += time_diff_ms
        cl.user_session.set("silent_duration_ms", silent_duration_ms)
        
        # Auto-process if silence exceeds timeout after user has spoken
        if silent_duration_ms >= SILENCE_TIMEOUT and is_speaking:
            cl.user_session.set("is_speaking", False)
            cl.user_session.set("audio_auto_ended", True)
            print("🔇 Silence detected after speech — auto-processing audio")
            await process_audio_input()
    else:
        # Audio is active, reset silence timer
        cl.user_session.set("silent_duration_ms", 0)
        if not is_speaking:
            cl.user_session.set("is_speaking", True)


# Shared audio processing function (used by both silence auto-end and manual stop)
async def process_audio_input():
    """Process recorded audio - transcribe and send to RAG pipeline"""
    audio_chunks = cl.user_session.get("audio_chunks")
    audio_handler = cl.user_session.get("audio_handler")
    
    if not audio_chunks or not audio_handler:
        await cl.Message(content="⚠️ Tidak ada audio yang terekam.").send()
        return
    
    # Convert chunks to WAV
    audio_buffer, duration = audio_handler.chunks_to_wav(audio_chunks)
    
    # Check minimum duration
    if duration < MIN_AUDIO_DURATION:
        await cl.Message(
            content=f"⚠️ Audio terlalu pendek ({duration:.1f}s). Silakan bicara lebih lama."
        ).send()
        return
    
    print(f"🎤 Audio recorded: {duration:.1f}s")
    
    try:
        # First show transcribing status (this will be replaced)
        status_msg = cl.Message(content='<span class="loading-text"><span class="loading-spinner"></span>Mentranskrip audio<span class="loading-dots"></span></span>')
        await status_msg.send()
        
        # Transcribe audio to text
        transcription = await cl.make_async(audio_handler.transcribe)(audio_buffer)
        
        if not transcription:
            status_msg.content = "⚠️ Tidak dapat mentranskripsi audio. Silakan coba lagi."
            await status_msg.update()
            return
        
        print(f"📝 Transcription: {transcription}")
        
        # Remove the status message by clearing it
        await status_msg.remove()
        
        # Show user's transcribed message FIRST
        await cl.Message(
            author="You",
            type="user_message",
            content=transcription,
        ).send()
        
        # Create NEW response message for RAG output
        response_msg = cl.Message(content='<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>')
        await response_msg.send()
        
        # Now process through RAG pipeline
        await process_question(transcription, response_msg)
        
    except Exception as e:
        print(f"Error transcribing audio: {str(e)}")
        error_msg = cl.Message(content="⚠️ Terjadi kesalahan saat memproses audio. Silakan coba lagi.")
        await error_msg.send()


@cl.on_audio_end
async def on_audio_end():
    """Process completed audio recording - transcribe and send to RAG"""
    # Skip if already auto-processed by silence detection
    if cl.user_session.get("audio_auto_ended"):
        print("🔇 Audio already auto-processed by silence detection, skipping on_audio_end")
        return
    
    await process_audio_input()


# Question Processing
async def process_question(user_question: str, msg: cl.Message = None):
    """Process user question through RAG pipeline"""
    retriever = cl.user_session.get("retriever")
    llm = cl.user_session.get("llm")
    
    if not retriever or not llm:
        await cl.Message(
            content="Sesi belum diinisialisasi. Silakan refresh halaman."
        ).send()
        return
    
    # Create new message if not provided
    start_time = time.time()
    if msg is None:
        loading_html = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
        msg = cl.Message(content=loading_html)
        await msg.send()
    else:
        # Update existing message with search status
        msg.content = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
        await msg.update()
    
    try:
        # Retrieve documents
        docs = await cl.make_async(retriever.invoke)(user_question)
        
        # Check if we have results
        if not docs:
            no_result_msg = ("Mohon maaf, saya tidak menemukan informasi yang relevan dengan pertanyaan Anda "
                          "dalam dokumen sekolah. Silakan coba dengan kata kunci lain atau hubungi "
                          "pihak sekolah secara langsung.")
            msg.content = no_result_msg
            await msg.update()
            log_query(user_question, no_result_msg, "no_result", "Tidak ada dokumen relevan", 0,
                      response_time=round(time.time() - start_time, 2))
            return
        
        # Format context
        context = format_docs(docs)
        
        # Generate answer - choose mode based on config
        if USE_STREAMING:
            # Streaming mode
            full_response = ""
            for token in llm.generate_stream(user_question, context):
                full_response += token
                msg.content = full_response
                await msg.stream_token(token)
        else:
            # Non-streaming mode
            full_response = await cl.make_async(llm.generate)(user_question, context)
            msg.content = full_response
        
        # Clean up double dots from LLM response (e.g. ".." → ".")
        import re
        full_response = re.sub(r'(?<!\.)\.\.(?!\.)', '.', full_response)
        msg.content = full_response
        
        # Final update
        await msg.update()
        
        # Extract top source from first retrieved document
        top_source = docs[0].metadata.get("source", None) if docs else None
        
        # Deteksi fallback: cek apakah LLM menjawab "informasi tidak tersedia" dll.
        # Hanya cek 200 karakter pertama untuk menghindari false positive
        # (frasa fallback di tengah/akhir jawaban valid tidak dianggap fallback)
        status = "success"
        response_start = full_response[:50].lower()
        for phrase in FALLBACK_PHRASES:
            if phrase in response_start:
                status = "no_result"
                print(f"⚠️ Fallback detected: '{phrase}' ditemukan di awal respons LLM → status diubah ke 'no_result'")
                break
        
        # Log query dengan status yang sudah dikoreksi
        log_query(user_question, full_response, status, None, len(docs), top_source,
                  response_time=round(time.time() - start_time, 2))
        
        # Generate context-aware query suggestions
        try:
            suggestions = await cl.make_async(llm.generate_suggestions)(
                user_question, docs, full_response
            )
            
            if suggestions:
                actions = []
                for suggestion in suggestions:
                    actions.append(cl.Action(
                        name="suggestion",
                        payload={"query": suggestion},
                        label=suggestion
                    ))
                msg.actions = actions
                await msg.update()
        except Exception as e:
            # Non-critical: if suggestions fail, answer is still displayed
            print(f"⚠️ Failed to add suggestions: {str(e)}")

        # Source documents in panel sidebar
        # if docs:
        #     source_elements = []f
        #     for i, doc in enumerate(docs, 1):
        #         source_name = doc.metadata.get("source", "Unknown")
        #         section = doc.metadata.get("section_title", "")
        #         content = doc.page_content
                
        #         # Truncate content for preview
        #         content_preview = content[:300] + "..." if len(content) > 300 else content
                
        #         source_elements.append(
        #             cl.Text(
        #                 name=f"📄 Sumber: {source_name}",
        #                 content=f"**Bagian:** {section}\n\n{content_preview}",
        #                 display="side"
        #             )
        #         )
            
        #     msg.elements = source_elements
        #     await msg.update()
    
    except RateLimitError as e:
        # Tampilkan toast notification untuk rate limit
        retry_msg = f" Silakan tunggu {e.retry_after} detik." if e.retry_after else ""
        error_content = (f"⚠️ **Layanan sedang sibuk**\n\n"
                      f"Mohon maaf, layanan sedang sibuk karena terlalu banyak permintaan.{retry_msg}\n\n"
                      f"Silakan coba lagi beberapa saat lagi.")
        msg.content = error_content
        await msg.update()
        log_query(user_question, error_content, "error", f"Rate limit: {str(e)}", 0,
                  response_time=round(time.time() - start_time, 2))
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        error_content = ("Mohon maaf, terjadi kendala teknis dalam memproses pertanyaan Anda. "
                      "Silakan coba beberapa saat lagi.")
        msg.content = error_content
        await msg.update()
        log_query(user_question, error_content, "error", str(e), 0,
                  response_time=round(time.time() - start_time, 2))


# Handle user text messages 
@cl.on_message
async def on_message(message: cl.Message):
    """Handle text message input"""
    user_question = message.content
    
    # Create loading message
    loading_html = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
    msg = cl.Message(content=loading_html)
    await msg.send()
    
    # Process through shared RAG pipeline
    await process_question(user_question, msg)


if __name__ == "__main__":
    print("Run with: chainlit run app.py -w")
