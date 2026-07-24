import os
import time
import logging
import soundfile as sf
import numpy as np  # Make sure numpy is imported
from pathlib import Path
from dataclasses import dataclass
from typing import List, Any
import base64
from sarvamai.play import save

# --- Added Dataclass ---
# Added this to make the script runnable without the external import
@dataclass
class PodcastScript:
    script: List[dict]
    source_document: str
    total_lines: int
    estimated_duration: str

# --- Corrected SarvamAI Import ---
try:
    from sarvamai import SarvamAI
except ImportError:
    print("SarvamAI SDK not installed. Install with: pip install sarvamai soundfile")
    SarvamAI = None
# --- End Correction ---


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AudioSegment:
    """Represents a single audio segment with metadata"""
    speaker: str
    text: str
    audio_data: Any
    duration: float
    file_path: str


class PodcastTTSGenerator:
    def __init__(self, lang_code: str = "en-IN", sample_rate: int = 24000):
        """
        Initialize Bulbul TTS with SarvamAI Client API.
        """
        if SarvamAI is None:
            raise ImportError("SarvamAI client not available. Please install with: pip install sarvamai soundfile")

        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise EnvironmentError("Please set your SarvamAI API key in environment variable 'SARVAM_API_KEY'.")

        # --- Corrected Client Initialization ---
        self.client = SarvamAI(api_subscription_key=api_key)
        # --- End Correction ---
        
        self.lang_code = lang_code
        self.sample_rate = sample_rate

        # Speaker voice map
        self.speaker_voices = {
            "Speaker 1": "anushka",  # Female
            "Speaker 2": "karun"    # Male
        }

        logger.info(f"✅ SarvamAI Bulbul initialized with lang_code={lang_code}, sample_rate={sample_rate}")

    # -------------------------------------------------------------

    def generate_podcast_audio(
        self,
        podcast_script: PodcastScript,
        output_dir: str = "outputs/podcast_audio_bulbul",
        combine_audio: bool = True,
        pause_duration: float = 0.25
    ) -> List[str]:
        """
        Generate multi-speaker podcast audio using Bulbul model.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"Generating podcast audio for {podcast_script.total_lines} segments")

        audio_segments = []
        output_files = []

        for i, line_dict in enumerate(podcast_script.script):
            speaker, dialogue = next(iter(line_dict.items()))

            logger.info(f"🎙️ [{speaker}] {dialogue[:80]}...")

            try:
                segment_path = os.path.join(
                    output_dir,
                    f"segment_{i+1:03d}_{speaker.replace(' ', '_').lower()}.wav"
                )

                self._convert_text_to_speech(
                    text=dialogue,
                    speaker=speaker,
                    target_language=self.lang_code,
                    output_path=segment_path
                )

                data, sr = sf.read(segment_path, dtype="float32")

                audio_segments.append(
                    AudioSegment(
                        speaker=speaker,
                        text=dialogue,
                        audio_data=data,
                        duration=len(data) / sr,
                        file_path=segment_path
                    )
                )

                output_files.append(segment_path)
                logger.info(f"✅ Segment {i+1} saved: {segment_path}")

            except Exception as e:
                logger.error(f"❌ Error generating segment {i+1}: {e}")
                continue

        if combine_audio and audio_segments:
            combined_path = self._combine_audio_segments(audio_segments, output_dir, pause_duration)
            output_files.append(combined_path)

        logger.info(f"🎧 Podcast generation complete! {len(output_files)} files created.")
        return output_files

    # -------------------------------------------------------------

    def _convert_text_to_speech(self, text: str, speaker: str, target_language: str, output_path: str):
        """
        Convert one line of text to speech using Bulbul (official API pattern).
        """
        try:
            voice = self.speaker_voices.get(speaker, "anushka")

            logger.info(f"🗣️ Converting text to speech (speaker={voice}, lang={target_language})")

            # This returns a TextToSpeechResponse object
            audio_response = self.client.text_to_speech.convert(
                target_language_code=target_language,
                text=text,
                model="bulbul:v2",
                speaker=voice
            )

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # --- THIS IS THE FINAL FIX ---
            # Use the SDK's 'save' function to correctly save the audio
            
            save(audio_response, output_path)
            
            # --- END OF FIX ---

            time.sleep(0.4)  # gentle rate-limit protection
            return output_path

        except Exception as e:
            logger.error(f"TTS conversion error for {speaker}: {e}")
            raise

    # -------------------------------------------------------------

    def _combine_audio_segments(
        self,
        segments: List[AudioSegment],
        output_dir: str,
        pause_duration: float = 0.25
    ) -> str:
        """
        Combine generated segments with pauses between speakers.
        """
        try:
            logger.info(f"🔊 Combining {len(segments)} segments with {pause_duration}s pauses")

            pause_samples = int(pause_duration * self.sample_rate)
            pause_audio = np.zeros(pause_samples, dtype=np.float32)

            all_audio = []
            for i, segment in enumerate(segments):
                all_audio.append(segment.audio_data)
                if i < len(segments) - 1:
                    all_audio.append(pause_audio)

            combined_audio = np.concatenate(all_audio)

            combined_path = os.path.join(output_dir, "complete_podcast.wav")
            sf.write(combined_path, combined_audio, self.sample_rate)

            duration = len(combined_audio) / self.sample_rate
            logger.info(f"✅ Combined podcast saved: {combined_path} ({duration:.1f}s)")

            return combined_path

        except Exception as e:
            logger.error(f"Error combining segments: {e}")
            raise

# -------------------------------------------------------------
# ✅ Example run
# -------------------------------------------------------------
if __name__ == "__main__":
    # Make sure your API key is set as an environment variable:
    # export SARVAM_API_KEY='your_actual_api_key_here'
    
    if not os.getenv("SARVAM_API_KEY"):
        print("🚨 Error: SARVAM_API_KEY environment variable not set.")
        print("Please set it before running the script:")
        print("export SARVAM_API_KEY='your_actual_api_key_here'")
    else:
        try:
            tts_generator = PodcastTTSGenerator(lang_code="en-IN")

            sample_script_data = {
                "script": [
                    {"Speaker 1": "Welcome everyone to our podcast! Today we're exploring artificial intelligence."},
                    {"Speaker 2": "Thank you! AI is transforming the world in fascinating ways."},
                    {"Speaker 1": "Let’s begin with how machine learning works."},
                    {"Speaker 2": "Machine learning allows computers to improve from experience without explicit programming."}
                ]
            }

            test_script = PodcastScript(
                script=sample_script_data["script"],
                source_document="AI Overview Test",
                total_lines=len(sample_script_data["script"]),
                estimated_duration="1 minute"
            )

            print("🎙️ Generating multi-speaker Bulbul podcast...")
            output_files = tts_generator.generate_podcast_audio(
                podcast_script=test_script,
                output_dir="./podcast_output_bulbul_client",
                combine_audio=True,
                pause_duration=0.25
            )

            print("\n✅ Generated Files:")
            for path in output_files:
                print(f"  - {path}")

            print("\n🎉 Podcast generation completed successfully!")

        except Exception as e:
            print(f"Error: {e}")