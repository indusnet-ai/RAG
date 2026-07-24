import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
import yt_dlp
from sarvamai import SarvamAI
import json
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

from services.doc_processor import DocumentChunk
from services.metrics import track_external_service_failure

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YouTubeTranscriber:
    def __init__(self, sarvam_api_key: str, youtube_api_key: Optional[str] = None):
        self.sarvam_api_key = sarvam_api_key
        self.youtube_api_key = youtube_api_key or os.getenv("YOUTUBE_API_KEY")
        self.client = SarvamAI(api_subscription_key=sarvam_api_key)
        self.temp_dir = Path(tempfile.gettempdir()) / "youtube_transcriber"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Initialize YouTube API client if key is available
        if self.youtube_api_key:
            self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
            logger.info("YouTubeTranscriber initialized with YouTube Data API v3")
        else:
            self.youtube = None
            logger.warning("YouTube API key not found, will use fallback methods")
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL"""
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
        else:
            video_id = None
        return video_id
    
    def get_video_info(self, url: str) -> dict:
        """Get video metadata using YouTube Data API (official, no bot detection)"""
        video_id = self.extract_video_id(url)
        
        if not video_id:
            return {
                'title': 'Unknown Title',
                'duration': 0,
                'uploader': 'Unknown',
                'upload_date': 'Unknown'
            }
        
        # Try YouTube Data API first (official, always works)
        if self.youtube:
            try:
                request = self.youtube.videos().list(
                    part="snippet,contentDetails",
                    id=video_id
                )
                response = request.execute()
                
                if response['items']:
                    video = response['items'][0]
                    
                    # Parse ISO 8601 duration (PT15M33S -> seconds)
                    duration_str = video['contentDetails']['duration']
                    duration = self._parse_iso_duration(duration_str)
                    
                    return {
                        'title': video['snippet']['title'],
                        'duration': duration,
                        'uploader': video['snippet']['channelTitle'],
                        'upload_date': video['snippet']['publishedAt'][:10].replace('-', '')
                    }
            except Exception as e:
                logger.warning(f"YouTube API failed: {e}, trying fallback...")
        
        # Fallback to yt-dlp (less reliable on servers)
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                    }
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', 'Unknown')
                }
        except Exception as e:
            logger.error(f"All methods failed to get video info: {e}")
            return {
                'title': 'Unknown Title',
                'duration': 0,
                'uploader': 'Unknown',
                'upload_date': 'Unknown'
            }
    
    def _parse_iso_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration to seconds (PT1H2M10S -> 3730)"""
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
    def get_cookies_file(self) -> Optional[str]:
        """Get cookies file path from env var (for production servers)"""
        # Check for direct file path
        cookies_path = os.getenv("YOUTUBE_COOKIES_PATH")
        if cookies_path and os.path.exists(cookies_path):
            logger.info(f"🍪 Using cookies file: {cookies_path}")
            return cookies_path

        logger.warning("⚠️  No cookies file found - set YOUTUBE_COOKIES_PATH env var")
        return None
    
    def download_audio(self, url: str) -> str:
        """Download audio using yt-dlp with advanced anti-bot measures"""
        url = url.split("?")[0]
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError("Could not extract video ID from URL")
        
        # Check for existing files
        for ext in ['.mp4', '.m4a', '.webm', '.opus']:
            expected_path = self.temp_dir / f"{video_id}{ext}"
            if expected_path.exists():
                logger.info(f"Audio already exists: {expected_path}")
                return str(expected_path)
        
        logger.info(f"Downloading audio from: {url}")
        
        cookies_file = self.get_cookies_file()  # ✅ ADD HERE (before ydl_opts)
        
        ydl_opts = {
    'format': 'bestaudio/best',
 
    'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
 
    'cookiefile': '/var/www/chatbot/suryavani/RAG-chatbot/cookies.txt',
 
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a'
    }],
 
    'js_runtimes': {
        'node': {
            'path': '/usr/local/bin/node'
        }
    },
 
    'remote_components': ['ejs:github'],
 
    'extractor_args': {
        'youtube': {
            'player_client': ['web'],
            'player_skip': ['configs']
        }
    },
 
    'http_headers': {
        'User-Agent': 'Mozilla/5.0'
    },
 
    'quiet': False,
    'no_warnings': False,
    'noplaylist': True,
 
    'retries': 10,
    'fragment_retries': 10,
    'skip_unavailable_fragments': True,
    'geo_bypass': True,
    'force_ipv4': True,
    'nocheckcertificate': True,
}
        
        if cookies_file:  # ✅ ADD HERE (after ydl_opts, before try block)
            ydl_opts['cookiefile'] = cookies_file
            logger.info("🍪 Using cookies for authentication")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                error_code = ydl.download([url])
        
                if error_code != 0:
                    raise Exception(f"yt-dlp download failed with error code: {error_code}")
        
            # Check for downloaded file
            for ext in ['.m4a', '.mp4', '.webm', '.opus']:
                check_path = self.temp_dir / f"{video_id}{ext}"
        
                if check_path.exists():
                    logger.info(f"✅ Audio downloaded successfully: {check_path}")
                    return str(check_path)
        
            raise FileNotFoundError("Audio file not found after download")
        
        except Exception as e:
            track_external_service_failure("youtube")
            logger.error(f"❌ Download failed: {e}")
            raise Exception(f"Failed to download audio from {url}: {str(e)}")
    
    def get_video_duration(self, url: str) -> float:
        """Get video duration in seconds"""
        info = self.get_video_info(url)
        return info.get('duration', 0)
    
    def transcribe_with_sarvam_batch(
        self, 
        audio_path: str, 
        language: str = "en-IN",
        with_diarization: bool = True,
        num_speakers: int = 2
    ) -> tuple:
        """Transcribe audio using Sarvam AI Batch API with speaker diarization"""
        
        logger.info(f"Creating Sarvam AI batch job (diarization={with_diarization}, speakers={num_speakers})...")
        
        try:
            # Create batch transcription job with diarization
            job = self.client.speech_to_text_job.create_job(
                language_code=language,
                model="saarika:v2.5",
                with_diarization=with_diarization,
                num_speakers=num_speakers if with_diarization else None
            )
            
            logger.info(f"Batch job created: {job.job_id}")
            
            # Upload audio file
            logger.info("Uploading audio file...")
            job.upload_files(file_paths=[audio_path])
            
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
            output_dir = self.temp_dir / f"output_{job.job_id}"
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
            
            logger.info("Transcription completed successfully")
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
        
        logger.info(f"Raw Sarvam API response structure: {json.dumps(data, indent=2)[:500]}")
        
        utterances = []
        
        # Extract utterances with speaker labels
        if isinstance(data, dict):
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
                utterance = {
                    'speaker': utt.get('speaker', 'SPEAKER_00'),
                    'text': utt.get('text', ''),
                    'start': utt.get('start', 0),
                    'end': utt.get('end', 0)
                }
                
                logger.info(f"Utterance: speaker={utterance['speaker']}, start={utterance['start']}, end={utterance['end']}, text={utterance['text'][:50]}...")
                
                utterances.append(utterance)
        
        if not utterances:
            logger.warning("No utterances found, falling back to simple transcript")
            transcript = self._extract_simple_transcript(output_dir)
            utterances = [{
                'speaker': 'SPEAKER_00',
                'text': transcript,
                'start': 0,
                'end': 0
            }]
        
        return utterances
    
    def _extract_simple_transcript(self, output_dir: Path) -> str:
        """Extract plain transcript without speaker labels"""
        
        json_files = list(output_dir.glob("*.json"))
        
        if not json_files:
            raise Exception("No transcript files found in output directory")
        
        with open(json_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract transcript text
        if isinstance(data, dict):
            if 'transcript' in data:
                return data['transcript']
            elif 'text' in data:
                return data['text']
            elif 'results' in data and isinstance(data['results'], list):
                if len(data['results']) > 0:
                    result = data['results'][0]
                    if 'transcript' in result:
                        return result['transcript']
                    elif 'text' in result:
                        return result['text']
                    elif 'utterances' in result:
                        return ' '.join([u.get('text', '') for u in result['utterances']])
            elif 'utterances' in data:
                return ' '.join([u.get('text', '') for u in data['utterances']])
        
        raise Exception("Could not extract transcript from API response")
    
    def _create_chunks_with_estimated_timestamps(
        self,
        transcript_text: str,
        video_id: str,
        url: str,
        video_duration: float,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ) -> List[DocumentChunk]:
        """Create chunks with estimated timestamps based on video duration"""
        
        chunks = []
        text_length = len(transcript_text)
        start = 0
        chunk_index = 0
        
        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = transcript_text[start:end]
            
            # Estimate timestamps based on position in text
            if text_length > 0:
                start_timestamp = (start / text_length) * video_duration
                end_timestamp = (end / text_length) * video_duration
            else:
                start_timestamp = 0
                end_timestamp = 0
            
            chunk_metadata = {
                'speakers': ['SPEAKER_00'],
                'start_timestamp': start_timestamp,
                'end_timestamp': end_timestamp,
                'speaker_count': 1,
                'video_url': url,
                'video_id': video_id,
                'transcription_service': 'sarvam_ai_batch',
                'timestamp_estimated': True
            }
            
            chunk = DocumentChunk(
                content=chunk_text,
                source_file=f"YouTube Video {video_id}",
                source_type="youtube",
                page_number=None,
                chunk_index=chunk_index,
                start_char=start,
                end_char=end - 1,
                metadata=chunk_metadata
            )
            chunks.append(chunk)
            chunk_index += 1
            
            start = max(start + chunk_size - chunk_overlap, end)
        
        return chunks
    
    def create_chunks_from_utterances(
        self,
        utterances: List[dict],
        video_id: str,
        url: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ) -> List[DocumentChunk]:
        """Create chunks from diarized utterances"""
        
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
            
            # Validate timestamps
            if start_time is None or end_time is None:
                logger.warning(f"Skipping utterance with missing timestamps: {text[:50]}...")
                continue
                
            # Ensure timestamps are numeric
            try:
                start_time = float(start_time)
                end_time = float(end_time)
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp format: start={start_time}, end={end_time}")
                start_time = 0
                end_time = 0
            
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
                    'video_url': url,
                    'video_id': video_id,
                    'transcription_service': 'sarvam_ai_batch'
                }
                
                chunk = DocumentChunk(
                    content=current_text.strip(),
                    source_file=f"YouTube Video {video_id}",
                    source_type="youtube",
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
                'video_url': url,
                'video_id': video_id,
                'transcription_service': 'sarvam_ai_batch'
            }
            
            chunk = DocumentChunk(
                content=current_text.strip(),
                source_file=f"YouTube Video {video_id}",
                source_type="youtube",
                page_number=None,
                chunk_index=chunk_index,
                start_char=start_char,
                end_char=start_char + len(current_text) - 1,
                metadata=chunk_metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def transcribe_youtube_video(
        self,
        url: str,
        cleanup_audio: bool = True,
        language: str = "en-IN",
        enable_diarization: bool = False,
        num_speakers: int = 1,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ) -> Tuple[List[DocumentChunk], str]:
        """
        Transcribe YouTube video and return chunks along with video title.
        
        Returns:
            Tuple[List[DocumentChunk], str]: (chunks, video_title)
        """
        url = url.split("?")[0]
        try:
            # Get video info using YouTube API (most reliable)
            video_info = self.get_video_info(url)
            video_title = video_info['title']
            video_duration = video_info['duration']
            
            logger.info(f"Processing video: {video_title} ({video_duration}s)")
            
            # Download audio
            audio_path = self.download_audio(url)
            video_id = self.extract_video_id(url)
            
            # Transcribe using Sarvam AI Batch API
            transcript_text, utterances = self.transcribe_with_sarvam_batch(
                audio_path, 
                language,
                with_diarization=False,
                num_speakers=1
            )
            
            # Create chunks with estimated timestamps
            chunks = self._create_chunks_with_estimated_timestamps(
                transcript_text,
                video_id,
                url,
                video_duration,
                chunk_size,
                chunk_overlap
            )
            
            logger.info(f"Transcription completed: {len(chunks)} chunks created")
            
            if cleanup_audio and os.path.exists(audio_path):
                os.unlink(audio_path)
                logger.info("Audio file cleaned up")
            
            return chunks, video_title
            
        except Exception as e:
            logger.error(f"Error transcribing YouTube video: {str(e)}")
            raise
    
    def cleanup_temp_files(self):
        try:
            if self.temp_dir.exists():
                for file in self.temp_dir.glob("*"):
                    if file.suffix in ['.m4a', '.mp4', '.webm', '.opus']:
                        file.unlink()
                logger.info("Temporary files cleaned up")
        except Exception as e:
            logger.warning(f"Could not clean up temp files: {e}")