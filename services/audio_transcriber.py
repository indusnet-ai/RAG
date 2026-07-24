

import logging
import os
from typing import List, Dict, Any
from pathlib import Path
import json
import subprocess
from sarvamai import SarvamAI

from services.doc_processor import DocumentChunk
from services.metrics import track_external_service_failure

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioTranscriber:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = SarvamAI(api_subscription_key=api_key)
        
        self.supported_formats = {
            '.mp3', '.wav', '.m4a', '.aac', '.ogg', 
            '.flac', '.wma', '.opus', '.mp4', '.mov', 
            '.avi', '.aiff', '.amr', '.webm'
        }
        
        logger.info("AudioTranscriber initialized with Sarvam AI Batch API (with Diarization)")
    
    def get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration in seconds using ffprobe"""
        try:
            result = subprocess.run(
                [
                    'ffprobe', 
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(audio_path)
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not determine audio duration: {e}")
            return 0.0
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "en-IN",
        enable_diarization: bool = False,
        num_speakers: int = 1,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ) -> List[DocumentChunk]:
        
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if audio_path.suffix.lower() not in self.supported_formats:
            raise ValueError(f"Unsupported audio format: {audio_path.suffix}")
        
        logger.info(f"Starting transcription for: {audio_path.name}")
        
        try:
            # Get audio duration for logging
            duration = self.get_audio_duration(audio_path)
            logger.info(f"Audio duration: {duration:.2f} seconds")
            
            # Use batch API for transcription
            transcript_text, utterances = self._call_batch_api(
                audio_path, 
                language,
                enable_diarization,
                num_speakers
            )
            
            logger.info(f"Transcription completed for: {audio_path.name}")
            
            # Create chunks based on whether diarization was used
            if enable_diarization and utterances:
                return self._create_chunks_from_utterances(
                    utterances,
                    audio_path.name,
                    chunk_size,
                    chunk_overlap
                )
            else:
                return self._create_chunks_from_text(
                    transcript_text, 
                    audio_path.name, 
                    chunk_size, 
                    chunk_overlap
                )
            
        except Exception as e:
            logger.error(f"Error transcribing audio {audio_path.name}: {str(e)}")
            raise
    
    def _call_batch_api(
        self, 
        audio_path: Path, 
        language: str,
        with_diarization: bool,
        num_speakers: int
    ) -> tuple:
        """Call Sarvam AI Batch API for transcription with optional diarization"""
        
        logger.info(f"Creating Sarvam AI batch job (diarization={with_diarization}, speakers={num_speakers})...")
        
        try:
            # Create batch transcription job
            job = self.client.speech_to_text_job.create_job(
                language_code=language,
                model="saarika:v2.5",
                with_diarization=with_diarization,
                num_speakers=num_speakers if with_diarization else None
            )
            
            logger.info(f"Batch job created: {job.job_id}")
            
            # Upload audio file
            logger.info("Uploading audio file...")
            job.upload_files(file_paths=[str(audio_path)])
            
            # Start the job
            logger.info("Starting transcription job...")
            job.start()
            
            # Wait for completion
            logger.info("Waiting for transcription to complete...")
            final_status = job.wait_until_complete()
            
            # Check if job failed
            if job.is_failed():
                raise Exception("Transcription job failed")
            
            logger.info(f"Job completed with status: {final_status}")
            
            # Download outputs to temp directory
            import tempfile
            output_dir = Path(tempfile.gettempdir()) / f"sarvam_output_{job.job_id}"
            output_dir.mkdir(exist_ok=True)
            
            logger.info("Downloading transcription results...")
            job.download_outputs(output_dir=str(output_dir))
            
            # Read the transcript from downloaded files
            if with_diarization:
                utterances = self._extract_diarized_transcript(output_dir)
                transcript_text = None
            else:
                transcript_text = self._extract_simple_transcript(output_dir)
                utterances = None
            
            # Cleanup output directory
            import shutil
            shutil.rmtree(output_dir)
            
            logger.info("Batch transcription completed successfully")
            return transcript_text, utterances
                
        except Exception as e:
            track_external_service_failure("sarvam")  # ✅ ADD THIS LINE
            logger.error(f"Batch transcription error: {str(e)}")
            raise Exception(f"Sarvam AI batch transcription failed: {str(e)}")
    
    def _extract_diarized_transcript(self, output_dir: Path) -> List[dict]:
        """Extract diarized transcript with speaker labels"""
        
        json_files = list(output_dir.glob("*.json"))
        
        if not json_files:
            raise Exception("No transcript files found in output directory")
        
        with open(json_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        utterances = []
        
        # Extract utterances with speaker labels
        if isinstance(data, dict):
            # Check for different possible structures
            if 'utterances' in data:
                utterances_data = data['utterances']
            elif 'results' in data and isinstance(data['results'], list):
                if len(data['results']) > 0 and 'utterances' in data['results'][0]:
                    utterances_data = data['results'][0]['utterances']
                else:
                    utterances_data = []
            else:
                utterances_data = []
            
            for utt in utterances_data:
                utterances.append({
                    'speaker': utt.get('speaker', 'SPEAKER_00'),
                    'text': utt.get('text', ''),
                    'start': utt.get('start', 0),
                    'end': utt.get('end', 0)
                })
        
        if not utterances:
            logger.warning("No utterances found in diarized output")
            # Fallback to simple transcript
            transcript = self._extract_simple_transcript(output_dir)
            utterances = [{
                'speaker': 'SPEAKER_00',
                'text': transcript,
                'start': 0,
                'end': 0
            }]
        
        return utterances
    
    def _extract_simple_transcript(self, output_dir: Path) -> str:
        """Extract simple transcript text without diarization"""
        
        json_files = list(output_dir.glob("*.json"))
        
        if not json_files:
            raise Exception("No transcript files found in output directory")
        
        with open(json_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            transcript = data.get('transcript', '')
            if not transcript and 'results' in data:
                results = data.get('results', [])
                if results and len(results) > 0:
                    transcript = results[0].get('transcript', '')
        elif isinstance(data, list):
            transcript = " ".join([item.get('transcript', '') for item in data if isinstance(item, dict)])
        else:
            transcript = str(data)
        
        if not transcript:
            raise Exception("Could not extract transcript from output files")
        
        return transcript
    
    def _create_chunks_from_utterances(
        self,
        utterances: List[dict],
        source_file: str,
        chunk_size: int,
        chunk_overlap: int
    ) -> List[DocumentChunk]:
        """Create chunks from diarized utterances (similar to AssemblyAI style)"""
        
        chunks = []
        current_text = ""
        current_speakers = []
        current_timestamps = []
        chunk_index = 0
        start_char = 0
        
        for utterance in utterances:
            speaker_label = utterance['speaker']
            text = utterance['text']
            start_time = utterance.get('start', 0)
            end_time = utterance.get('end', 0)
            
            # Format with speaker and text
            speaker_text = f"{speaker_label}: {text}\n"
            
            # Check if adding this utterance exceeds chunk size
            if len(current_text + speaker_text) > chunk_size and current_text:
                # Create chunk
                chunk_metadata = {
                    'speakers': list(set(current_speakers)),
                    'start_timestamp': current_timestamps[0] if current_timestamps else None,
                    'end_timestamp': current_timestamps[-1] if current_timestamps else None,
                    'speaker_count': len(set(current_speakers)),
                    'transcription_service': 'sarvam_ai_batch'
                }
                
                chunk = DocumentChunk(
                    content=current_text.strip(),
                    source_file=source_file,
                    source_type='audio',
                    page_number=None,
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=start_char + len(current_text) - 1,
                    metadata=chunk_metadata
                )
                chunks.append(chunk)
                
                # Start new chunk with overlap
                overlap_text = current_text[-chunk_overlap:] if chunk_overlap > 0 else ""
                current_text = overlap_text + speaker_text
                start_char += len(current_text) - len(overlap_text) - len(speaker_text)
                chunk_index += 1
                
                current_speakers = [speaker_label]
                current_timestamps = [start_time, end_time]
            else:
                current_text += speaker_text
                current_speakers.append(speaker_label)
                current_timestamps.extend([start_time, end_time])
        
        # Add final chunk
        if current_text.strip():
            chunk_metadata = {
                'speakers': list(set(current_speakers)),
                'start_timestamp': current_timestamps[0] if current_timestamps else None,
                'end_timestamp': current_timestamps[-1] if current_timestamps else None,
                'speaker_count': len(set(current_speakers)),
                'transcription_service': 'sarvam_ai_batch'
            }
            
            chunk = DocumentChunk(
                content=current_text.strip(),
                source_file=source_file,
                source_type='audio',
                page_number=None,
                chunk_index=chunk_index,
                start_char=start_char,
                end_char=start_char + len(current_text) - 1,
                metadata=chunk_metadata
            )
            chunks.append(chunk)
        
        logger.info(f"Created {len(chunks)} chunks from {len(utterances)} utterances")
        return chunks
    
    def _create_chunks_from_text(
        self,
        transcript_text: str,
        source_file: str,
        chunk_size: int,
        chunk_overlap: int
    ) -> List[DocumentChunk]:
        """Split transcript text into chunks (no diarization)"""
        
        if not transcript_text.strip():
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(transcript_text):
            end = min(start + chunk_size, len(transcript_text))
            
            # Try to break at sentence boundary
            if end < len(transcript_text):
                last_period = transcript_text.rfind('.', start, end)
                last_newline = transcript_text.rfind('\n', start, end)
                last_question = transcript_text.rfind('?', start, end)
                last_exclamation = transcript_text.rfind('!', start, end)
                
                boundary = max(last_period, last_newline, last_question, last_exclamation)
                if boundary > start + chunk_size * 0.5:
                    end = boundary + 1
            
            chunk_text = transcript_text[start:end].strip()
            
            if chunk_text:
                chunk_metadata = {
                    'transcription_service': 'sarvam_ai_batch',
                    'word_count': len(chunk_text.split())
                }
                
                chunk = DocumentChunk(
                    content=chunk_text,
                    source_file=source_file,
                    source_type='audio',
                    page_number=None,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end - 1,
                    metadata=chunk_metadata
                )
                chunks.append(chunk)
                chunk_index += 1
            
            start = max(start + chunk_size - chunk_overlap, end)
        
        logger.info(f"Created {len(chunks)} chunks from transcript")
        return chunks
    
    def get_transcript_summary(
        self, 
        audio_path: str, 
        language: str = "en-IN",
        enable_diarization: bool = True,
        num_speakers: int = 2
    ) -> Dict[str, Any]:
        """Get basic summary information about the transcription"""
        try:
            audio_path = Path(audio_path)
            
            if not audio_path.exists():
                return {"error": "Audio file not found"}
            
            # Get audio duration
            duration = self.get_audio_duration(audio_path)
            
            # Get transcription
            transcript_text, utterances = self._call_batch_api(
                audio_path, 
                language,
                enable_diarization,
                num_speakers
            )
            
            # Count speakers if diarization was used
            speaker_info = {}
            if utterances:
                speakers = list(set([u['speaker'] for u in utterances]))
                speaker_info = {
                    'num_speakers_detected': len(speakers),
                    'speakers': speakers
                }
            
            # Get full text for word count
            if transcript_text:
                full_text = transcript_text
            else:
                full_text = " ".join([u['text'] for u in utterances])
            
            summary_info = {
                'file_name': audio_path.name,
                'file_size_mb': round(audio_path.stat().st_size / (1024 * 1024), 2),
                'duration_seconds': round(duration, 2),
                'word_count': len(full_text.split()) if full_text else 0,
                'character_count': len(full_text) if full_text else 0,
                'transcription_service': 'sarvam_ai_batch',
                'diarization_enabled': enable_diarization,
                **speaker_info,
                'preview': full_text[:200] + '...' if len(full_text) > 200 else full_text
            }
            
            return summary_info
            
        except Exception as e:
            logger.error(f"Error getting transcript summary: {str(e)}")
            return {"error": str(e)}
    
    def batch_transcribe(
        self, 
        audio_paths: List[str],
        language: str = "en-IN",
        enable_diarization: bool = True,
        num_speakers: int = 2
    ) -> List[List[DocumentChunk]]:
        """Transcribe multiple audio files"""
        all_chunks = []
        for audio_path in audio_paths:
            try:
                chunks = self.transcribe_audio(
                    audio_path, 
                    language=language,
                    enable_diarization=enable_diarization,
                    num_speakers=num_speakers
                )
                all_chunks.append(chunks)
                logger.info(f"Successfully transcribed {audio_path}: {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to transcribe {audio_path}: {str(e)}")
                all_chunks.append([])
        
        return all_chunks


if __name__ == "__main__":
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("Please set SARVAM_API_KEY environment variable")
        exit(1)
    
    transcriber = AudioTranscriber(api_key)
    
    try:
        audio_file = "data/harvard.wav"

        # Get summary with diarization
        summary = transcriber.get_transcript_summary(
            audio_file,
            enable_diarization=True,
            num_speakers=2
        )
        print(f"Transcript Summary: {json.dumps(summary, indent=2)}")
        
        # Full transcription with diarization
        chunks = transcriber.transcribe_audio(
            audio_file, 
            language="en-IN",
            enable_diarization=True,
            num_speakers=2
        )
        
        print(f"\nTranscription Results:")
        print(f"Generated {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks[:3]):
            print(f"\nChunk {i+1}:")
            print(f"Speakers: {chunk.metadata.get('speakers', [])}")
            print(f"Content: {chunk.content[:200]}...")
        
    except Exception as e:
        print(f"Error in transcription example: {e}")