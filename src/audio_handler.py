import io
import wave
import numpy as np
from groq import Groq
from src.config import GROQ_API_KEY, STT_MODEL_NAME

# Configuration for silence detection
SILENCE_THRESHOLD = 2500  # Adjust for quieter/louder environments
SILENCE_TIMEOUT = 2000.0  # ms of silence to consider turn finished
MIN_AUDIO_DURATION = 1.0  # Minimum audio duration in seconds


class AudioHandler:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = STT_MODEL_NAME
        print(f"✅ AudioHandler initialized: {self.model}")
    
    # Transcribe audio to Indonesian text using Groq Whisper
    def transcribe(self, audio_buffer: bytes, mime_type: str = "audio/wav") -> str:
        audio_file = ("audio.wav", audio_buffer, mime_type)
        
        response = self.client.audio.transcriptions.create(
            file=audio_file,
            model=self.model,
            language="id",
            response_format="text"
        )
        
        return response.strip() if response else ""
    
    # Convert audio chunks to WAV format
    def chunks_to_wav(self, audio_chunks: list, sample_rate: int = 16000) -> tuple[bytes, float]:
        if not audio_chunks:
            return b"", 0.0
            
        # Concatenate all chunks
        concatenated = np.concatenate(audio_chunks)
        
        # Calculate duration
        duration = len(concatenated) / sample_rate
        
        # Create WAV buffer
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit (2 bytes per sample)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(concatenated.tobytes())
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue(), duration


def get_audio_handler() -> AudioHandler:
    return AudioHandler()
