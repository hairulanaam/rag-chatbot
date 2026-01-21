import chainlit as cl
from src.rag_chain import PineconeRetriever, GroqLLM, format_docs, RateLimitError

# Configuration
USE_STREAMING = True  # Set False untuk non-streaming mode

# Initialize the chat session
@cl.on_chat_start
async def on_chat_start():
    # Welcome message
    await cl.Message(
        content="""**Selamat datang di Layanan Informasi SD Integral Luqman Al Hakim Situbondo**

Saya adalah admin virtual yang siap membantu Anda mendapatkan informasi seputar sekolah kami.

Silakan ajukan pertanyaan Anda!"""
    ).send()
    
    # Initialize components
    try:
        retriever = PineconeRetriever(k=4)
        llm = GroqLLM()
        
        cl.user_session.set("retriever", retriever)
        cl.user_session.set("llm", llm)
        
        print("Chat session initialized with streaming support")
        
    except Exception as e:
        await cl.Message(
            content=f"Terjadi kesalahan saat inisialisasi: {str(e)}"
        ).send()

# Handle user messages 
@cl.on_message
async def on_message(message: cl.Message):
    retriever = cl.user_session.get("retriever")
    llm = cl.user_session.get("llm")
    
    if not retriever or not llm:
        await cl.Message(
            content="Sesi belum diinisialisasi. Silakan refresh halaman."
        ).send()
        return
    
    user_question = message.content
    
    # Create message for streaming
    msg = cl.Message(content="")
    await msg.send()
    
    try:
        # Retrieve relevant documents
        docs = await cl.make_async(retriever.invoke)(user_question)
        
        # Check if we have results
        if not docs:
            msg.content = ("Mohon maaf, saya tidak menemukan informasi yang relevan dengan pertanyaan Anda "
                          "dalam dokumen sekolah. Silakan coba dengan kata kunci lain atau hubungi "
                          "pihak sekolah secara langsung.")
            await msg.update()
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
            # Non-streaming mode - generate() returns complete string
            full_response = await cl.make_async(llm.generate)(user_question, context)
            msg.content = full_response
        
        # Final update
        await msg.update()
        
        # Source documents in panel sidebar
        # if docs:
        #     source_elements = []
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
        
        await cl.Message(
            content=f"⚠️ **Layanan sedang sibuk**\n\n"
                    f"Mohon maaf, layanan sedang sibuk karena terlalu banyak permintaan.{retry_msg}\n\n"
                    f"Silakan coba lagi beberapa saat lagi."
        ).send()
        
        # Update message with rate limit info
        msg.content = ""
        await msg.update()
            
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        msg.content = ("Mohon maaf, terjadi kendala teknis dalam memproses pertanyaan Anda. "
                      "Silakan coba beberapa saat lagi.")
        await msg.update()


if __name__ == "__main__":
    print("Run with: chainlit run app.py -w")
