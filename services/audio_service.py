from services.audio_transcriber import AudioTranscriber
from uuid import uuid4
from typing import List
import os
import logging

logger = logging.getLogger(__name__)


class AudioService:
    def __init__(self, sarvam_api_key: str = None, max_workers: int = 3):
        """
        Initialize AudioService with transcription support
        
        Args:
            sarvam_api_key: Sarvam AI API key (if None, reads from env)
            max_workers: Number of parallel workers for batch processing (default: 3)
        """
        api_key = sarvam_api_key or os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise ValueError("SARVAM_API_KEY not provided and not found in environment")
        
        self.transcriber = AudioTranscriber(api_key=api_key)
        self.max_workers = max_workers
        logger.info(f"AudioService initialized")

    def process_uploaded_audio(
        self, 
        temp_path: str, 
        original_name: str,
        language: str = "en-IN",
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ):
        """
        Process uploaded audio file - system handles everything automatically!
        
        Args:
            temp_path: Path to temporary audio file
            original_name: Original filename
            language: Language code (default: "en-IN")
            chunk_size: Size of text chunks (default: 1000)
            chunk_overlap: Overlap between chunks (default: 100)
            
        Returns:
            List of DocumentChunk instances with transcribed content
            
        Note:
            The system automatically:
            - Enables speaker detection (diarization)
            - Detects the number of speakers
            - Chunks the transcript optimally
            - Preserves speaker labels and timestamps
            
            You don't need to specify anything - it just works!
        """
        logger.info(f"🎵 Processing audio: {original_name}")
        
        # Always enable diarization and let the API auto-detect speakers
        # This gives the best results without requiring user input
        enable_diarization = True
        num_speakers = None  # Let API auto-detect
        
        logger.info(f"🎙️ Transcribing with automatic speaker detection...")
        
        # Transcribe audio with automatic speaker detection
        chunks = self.transcriber.transcribe_audio(
            audio_path=temp_path,
            language=language,
            enable_diarization=enable_diarization,
            num_speakers=num_speakers if num_speakers else 2,  # API default
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Ensure chunks have correct metadata
        for idx, chunk in enumerate(chunks):
            chunk.source_file = original_name
            chunk.chunk_index = idx
        
        # Log what was detected
        speakers_detected = set()
        for chunk in chunks:
            if chunk.metadata and 'speakers' in chunk.metadata:
                speakers_detected.update(chunk.metadata['speakers'])
        
        if speakers_detected:
            logger.info(f"🎤 Auto-detected {len(speakers_detected)} speaker(s): {sorted(list(speakers_detected))}")
        
        logger.info(f"✅ Transcription complete: {len(chunks)} chunks created")
        
        return chunks
    
    def get_audio_info(
        self,
        temp_path: str,
        language: str = "en-IN"
    ):
        """
        Get summary information about audio file
        
        Args:
            temp_path: Path to temporary audio file
            language: Language code (default: "en-IN")
            
        Returns:
            Dictionary with audio metadata and transcription preview
        """
        # Always enable diarization for info - we want to show what's in the audio
        return self.transcriber.get_transcript_summary(
            audio_path=temp_path,
            language=language,
            enable_diarization=True,
            num_speakers=2  # API default
        )
    
    def batch_process_audio(
        self,
        audio_paths: List[str],
        language: str = "en-IN"
    ):
        """
        Process multiple audio files in batch
        
        Args:
            audio_paths: List of audio file paths
            language: Language code (default: "en-IN")
            
        Returns:
            List of lists of DocumentChunk instances
        """
        # Always enable diarization for best results
        return self.transcriber.batch_transcribe(
            audio_paths=audio_paths,
            language=language,
            enable_diarization=True,
            num_speakers=2  # API default
        )