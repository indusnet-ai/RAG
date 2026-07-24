import os
import logging
from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SpeechToTextService:
    def __init__(self):
        """Initialize SarvamAI STT client"""
        self.api_key = os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY missing in environment variables")

        try:
            self.client = SarvamAI(api_subscription_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize SarvamAI: {e}")
            raise e

    def transcribe(self, audio_file_path: str) -> str | None:
        """
        Convert speech to text using SarvamAI Saaras v2.5
        Args:
            audio_file_path: Path to audio file (wav, webm, mp3, etc.)
        Returns:
            transcript (str) or None
        """
        try:
            with open(audio_file_path, "rb") as audio:
                response = self.client.speech_to_text.translate(
                    file=audio,
                    model="saaras:v2.5"
                )

            return getattr(response, "transcript", None)

        except Exception as e:
            logger.error(f"Speech-to-text error: {e}")
            return None