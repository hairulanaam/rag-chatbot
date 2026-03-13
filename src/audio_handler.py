import io
import wave
import numpy as np
from groq import Groq
from src.config import GROQ_API_KEY, STT_MODEL_NAME, STT_PROMPT

MIN_AUDIO_DURATION = 1.0  # Minimum audio duration in seconds
MIN_AUDIO_ENERGY = 300    # Minimum RMS energy to consider as speech (not silence/noise)

# Known Whisper hallucination phrases (case-insensitive match)
# Whisper often produces these when audio has low signal or is mostly silence
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
    
    # Check if audio has enough energy to be speech (not just silence/noise)
    def has_speech_energy(self, audio_chunks: list) -> bool:
        if not audio_chunks:
            return False
        concatenated = np.concatenate(audio_chunks)
        rms = int(np.sqrt(np.mean(concatenated.astype(np.float64) ** 2)))
        print(f"🔊 Audio RMS energy: {rms} (threshold: {MIN_AUDIO_ENERGY})")
        return rms >= MIN_AUDIO_ENERGY
    
    # Check if transcription is a known Whisper hallucination
    def is_hallucination(self, text: str) -> bool:
        import string
        normalized = text.strip().lower().strip(string.punctuation + " ")
        for phrase in WHISPER_HALLUCINATIONS:
            if normalized == phrase or normalized.startswith(phrase):
                print(f"🚫 Whisper hallucination detected: '{text}'")
                return True
        return False
    
    # Transcribe audio to Indonesian text using Groq Whisper
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
        
        # Filter known hallucinations
        if text and self.is_hallucination(text):
            return ""
        
        return text
    
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

