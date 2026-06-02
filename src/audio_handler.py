import io
import wave
import numpy as np
from groq import Groq
from src.config import GROQ_API_KEY, STT_MODEL_NAME, STT_PROMPT

MIN_AUDIO_DURATION = 1.0
MIN_AUDIO_ENERGY = 300

WHISPER_HALLUCINATIONS = [
    "terima kasih",
    "terima kasih telah menonton",
    "terima kasih sudah menonton",
    "subtitle by",
    "subtitles by",
    "sampai jumpa",
    "selamat tinggal",
    "salam",
    "jangan lupa subscribe",
    "jangan lupa like",
    "jangan lupa komen",
    "subscribe, like, komen",
    "like, komen dan share",
    "SUBSCRIBE, LIKE, KOMEN, SHARE",
]

class AudioHandler:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = STT_MODEL_NAME
        print(f"✅ AudioHandler initialized: {self.model}")

    def has_speech_energy(self, audio_chunks: list) -> bool:
        if not audio_chunks:
            return False
        concatenated = np.concatenate(audio_chunks)
        rms = int(np.sqrt(np.mean(concatenated.astype(np.float64) ** 2)))
        print(f"🔊 Audio RMS energy: {rms} (threshold: {MIN_AUDIO_ENERGY})")
        return rms >= MIN_AUDIO_ENERGY
    
    def is_hallucination(self, text: str) -> bool:
        import string
        normalized = text.strip().lower().strip(string.punctuation + " ")
        for phrase in WHISPER_HALLUCINATIONS:
            if normalized == phrase or normalized.startswith(phrase):
                print(f"🚫 Whisper hallucination detected: '{text}'")
                return True
        return False

    def transcribe(self, audio_buffer: bytes, mime_type: str = "audio/wav") -> str:
        audio_file = ("audio.wav", audio_buffer, mime_type)
        
        response = self.client.audio.transcriptions.create(
            file=audio_file,
            model=self.model,
            language="id",
            response_format="text",
            prompt=STT_PROMPT,
            temperature=0.0
        )
        
        text = response.strip() if response else ""
        
        if text and self.is_hallucination(text):
            return ""
        
        return text
    
    def transcribe_chunks(self, audio_chunks: list, sample_rate: int = 16000) -> str:
        """Transcribe accumulated audio chunks for interim/streaming display.
        Returns transcribed text or empty string on failure."""
        if not audio_chunks:
            return ""
        
        try:
            wav_bytes, duration = self.chunks_to_wav(audio_chunks, sample_rate)

            if duration < 0.5:
                return ""
            
            text = self.transcribe(wav_bytes)
            return text if text else ""
        except Exception as e:
            print(f"⚠️ Interim transcription error: {e}")
            return ""
    
    def chunks_to_wav(self, audio_chunks: list, sample_rate: int = 16000) -> tuple[bytes, float]:
        if not audio_chunks:
            return b"", 0.0
            
        concatenated = np.concatenate(audio_chunks)
        
        duration = len(concatenated) / sample_rate
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1) 
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(concatenated.tobytes())
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue(), duration


def get_audio_handler() -> AudioHandler:
    return AudioHandler()