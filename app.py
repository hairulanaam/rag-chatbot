import chainlit as cl
import numpy as np
import time
import asyncio
from src.rag_chain import PineconeRetriever, GroqLLM, format_docs, RateLimitError
from src.database import log_query
from src.audio_handler import AudioHandler, MIN_AUDIO_DURATION, MIN_AUDIO_ENERGY
from src.config import FALLBACK_PHRASES

USE_STREAMING = True

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

@cl.on_chat_start
async def on_chat_start():
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

@cl.action_callback("suggestion")
async def on_suggestion(action: cl.Action):
    suggestion_query = action.payload["query"]
    
    await cl.Message(
        author="You",
        type="user_message",
        content=suggestion_query,
    ).send()
    
    # Process the suggestion through RAG pipeline
    await process_question(suggestion_query)

STREAMING_TRANSCRIBE_INTERVAL = 2.0 

@cl.on_audio_start
async def on_audio_start():
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("last_transcribe_time", time.time())
    cl.user_session.set("interim_text", "")
    cl.user_session.set("is_transcribing", False)

    streaming_msg = cl.Message(content='<div id="voice-interim-bridge" data-text="" data-recording="true" style="display:none"></div>Mendengarkan...')
    await streaming_msg.send()
    cl.user_session.set("streaming_msg", streaming_msg)
    
    return True


async def _do_interim_transcription():
    audio_chunks = cl.user_session.get("audio_chunks")
    audio_handler = cl.user_session.get("audio_handler")
    streaming_msg = cl.user_session.get("streaming_msg")
    
    if not audio_chunks or not audio_handler or not streaming_msg:
        return
    
    chunks_copy = list(audio_chunks)
    
    try:
        text = await cl.make_async(audio_handler.transcribe_chunks)(chunks_copy)
        
        if text:
            import html
            cl.user_session.set("interim_text", text)
            escaped = html.escape(text, quote=True)
            streaming_msg.content = f'<div id="voice-interim-bridge" data-text="{escaped}" data-recording="true" style="display:none"></div>Mendengarkan...'
            await streaming_msg.update()
    except Exception as e:
        print(f"⚠️ Interim transcription error: {e}")
    finally:
        cl.user_session.set("is_transcribing", False)


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    audio_chunks = cl.user_session.get("audio_chunks")
    audio_chunk = np.frombuffer(chunk.data, dtype=np.int16)
    
    if audio_chunks is not None:
        audio_chunks.append(audio_chunk)

    last_time = cl.user_session.get("last_transcribe_time", 0)
    is_transcribing = cl.user_session.get("is_transcribing", False)
    now = time.time()
    
    if (now - last_time) >= STREAMING_TRANSCRIBE_INTERVAL and not is_transcribing:
        cl.user_session.set("last_transcribe_time", now)
        cl.user_session.set("is_transcribing", True)
        asyncio.create_task(_do_interim_transcription())

async def process_audio_input():
    audio_chunks = cl.user_session.get("audio_chunks")
    audio_handler = cl.user_session.get("audio_handler")
    streaming_msg = cl.user_session.get("streaming_msg")
    
    if not audio_chunks or not audio_handler:
        if streaming_msg:
            await streaming_msg.remove()
        await cl.Message(content="⚠️ Tidak ada audio yang terekam.").send()
        return
    
    if streaming_msg:
        interim_text = cl.user_session.get("interim_text", "")
        if interim_text:
            streaming_msg.content = f'<span class="loading-text"><span class="loading-spinner"></span>Memfinalisasi transkripsi<span class="loading-dots"></span></span>\n\n> {interim_text}'
        else:
            streaming_msg.content = '<span class="loading-text"><span class="loading-spinner"></span>Mentranskrip audio<span class="loading-dots"></span></span>'
        await streaming_msg.update()
    
    has_energy = audio_handler.has_speech_energy(audio_chunks)
    
    if not has_energy:
        if streaming_msg:
            streaming_msg.content = "⚠️ Tidak terdeteksi suara. Silakan bicara lebih keras dan coba lagi."
            await streaming_msg.update()
        else:
            await cl.Message(
                content="⚠️ Tidak terdeteksi suara. Silakan bicara lebih keras dan coba lagi."
            ).send()
        return

    audio_buffer, duration = audio_handler.chunks_to_wav(audio_chunks)

    duration_passed = duration >= MIN_AUDIO_DURATION
    
    if not duration_passed:
        if streaming_msg:
            streaming_msg.content = f"⚠️ Audio terlalu pendek ({duration:.1f}s). Silakan bicara lebih lama."
            await streaming_msg.update()
        else:
            await cl.Message(
                content=f"⚠️ Audio terlalu pendek ({duration:.1f}s). Silakan bicara lebih lama."
            ).send()
        return
    
    print(f"🎤 Audio recorded: {duration:.1f}s")
    
    try:
        transcription = await cl.make_async(audio_handler.transcribe)(audio_buffer)
        
        if not transcription:
            if streaming_msg:
                streaming_msg.content = "Tidak terdeteksi pertanyaan. Silakan bicara dengan jelas dan coba lagi."
                await streaming_msg.update()
            return
        
        print(f"📝 Final Transcription: {transcription}")
        
        if streaming_msg:
            await streaming_msg.remove()
        
        await cl.Message(
            author="You",
            type="user_message",
            content=transcription,
        ).send()
        
        response_msg = cl.Message(content='<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>')
        await response_msg.send()
        
        await process_question(transcription, response_msg)
        
    except Exception as e:
        print(f"Error transcribing audio: {str(e)}")
        if streaming_msg:
            streaming_msg.content = "⚠️ Terjadi kesalahan saat memproses audio. Silakan coba lagi."
            await streaming_msg.update()
        else:
            error_msg = cl.Message(content="⚠️ Terjadi kesalahan saat memproses audio. Silakan coba lagi.")
            await error_msg.send()


@cl.on_audio_end
async def on_audio_end():
    await process_audio_input()


async def process_question(user_question: str, msg: cl.Message = None):
    retriever = cl.user_session.get("retriever")
    llm = cl.user_session.get("llm")
    
    if not retriever or not llm:
        await cl.Message(
            content="Sesi belum diinisialisasi. Silakan refresh halaman."
        ).send()
        return
    
    start_time = time.time()
    if msg is None:
        loading_html = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
        msg = cl.Message(content=loading_html)
        await msg.send()
    else:
        msg.content = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
        await msg.update()
    
    try:
        docs = await cl.make_async(retriever.invoke)(user_question)
        if not docs:
            no_result_msg = ("Mohon maaf, saya tidak menemukan informasi yang relevan dengan pertanyaan Anda "
                          "dalam dokumen sekolah. Silakan coba dengan kata kunci lain atau hubungi "
                          "pihak sekolah secara langsung.")
            msg.content = no_result_msg
            await msg.update()
            log_query(user_question, no_result_msg, "no_result", "Tidak ada dokumen relevan", 0,
                      response_time=round(time.time() - start_time, 2))
            return
        
        context = format_docs(docs)
        
        if USE_STREAMING:
            full_response = ""
            for token in llm.generate_stream(user_question, context):
                full_response += token
                msg.content = full_response
                await msg.stream_token(token)
        else:
            full_response = await cl.make_async(llm.generate)(user_question, context)
            msg.content = full_response
        
        import re
        full_response = re.sub(r'(?<!\.)\.\.(?!\.)', '.', full_response)
        msg.content = full_response
        
        await msg.update()
        top_source = docs[0].metadata.get("source", None) if docs else None
        
        status = "success"
        response_start = full_response[:50].lower()
        for phrase in FALLBACK_PHRASES:
            if phrase in response_start:
                status = "no_result"
                print(f"⚠️ Fallback detected: '{phrase}' ditemukan di awal respons LLM → status diubah ke 'no_result'")
                break
        
        log_query(user_question, full_response, status, None, len(docs), top_source,
                  response_time=round(time.time() - start_time, 2))
        
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
            print(f"⚠️ Failed to add suggestions: {str(e)}")
    
    except RateLimitError as e:
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

@cl.on_message
async def on_message(message: cl.Message):
    user_question = message.content
    
    loading_html = '<span class="loading-text"><span class="loading-spinner"></span>Mencari dokumen<span class="loading-dots"></span></span>'
    msg = cl.Message(content=loading_html)
    await msg.send()
    await process_question(user_question, msg)

if __name__ == "__main__":
    print("Run with: chainlit run app.py -w")
