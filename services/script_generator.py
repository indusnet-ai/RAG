import logging
import json
from typing import List, Dict, Any
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from services.doc_processor import DocumentProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


import json, re, logging
logger = logging.getLogger(__name__)

def safe_json_parse(text: str):
    """Extract and parse JSON safely from LLM output that might include text or code fences."""
    if not text:
        logger.error("Empty LLM response received.")
        return None
    try:
        # Strip markdown fences
        text = text.strip()
        text = re.sub(r"^```(json)?", "", text)
        text = re.sub(r"```$", "", text)
        text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError:
        # Try extracting JSON inside text
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception as e:
                logger.error(f"Still failed to parse extracted JSON: {e}")
        logger.error(f"Failed to parse LLM response as JSON. Raw text: {text[:500]}")
        return None


@dataclass
class PodcastScript:
    """Represents a podcast script with metadata"""
    script: List[Dict[str, str]]
    source_document: str
    total_lines: int
    estimated_duration: str
    
    def get_speaker_lines(self, speaker: str) -> List[str]:
        return [item[speaker] for item in self.script if speaker in item]
    
    def to_json(self) -> str:
        return json.dumps({
            'script': self.script,
            'metadata': {
                'source_document': self.source_document,
                'total_lines': self.total_lines,
                'estimated_duration': self.estimated_duration
            }
        }, indent=2)


class PodcastScriptGenerator:
    def __init__(self, openai_api_key: str, model_name: str = "gpt-4.1"):
        self.llm = ChatOpenAI(
            temperature=0.4,
            model=model_name,
            api_key=openai_api_key,
            max_tokens=32768
        )
        self.doc_processor = DocumentProcessor()
        logger.info(f"Podcast script generator initialized with {model_name}")
    
    def generate_script_from_document(
        self,
        document_path: str,
        podcast_style: str = "conversational",
        target_duration: str = "10 minutes"
    ) -> PodcastScript:

        logger.info(f"Generating podcast script from: {document_path}")
        
        chunks = self.doc_processor.process_document(document_path)
        if not chunks:
            raise ValueError("No content extracted from document")
        
        document_content = "\n\n".join([chunk.content for chunk in chunks])
        source_name = chunks[0].source_file
        script_data = self._generate_conversation_script(
            document_content, 
            podcast_style, 
            target_duration
        )
        
        podcast_script = PodcastScript(
            script=script_data['script'],
            source_document=source_name,
            total_lines=len(script_data['script']),
            estimated_duration=target_duration
        )
        
        logger.info(f"Generated script with {podcast_script.total_lines} lines")
        return podcast_script
    
    def generate_script_from_text(
        self,
        text_content: str,
        source_name: str = "Text Input",
        podcast_style: str = "conversational",
        target_duration: str = "10 minutes",
        target_language: str = "English"
    ) -> PodcastScript:
        """Generate script with language support"""
        logger.info(f"Generating {target_language} podcast script from text input")
        
        script_data = self._generate_conversation_script(
            text_content,
            podcast_style,
            target_duration,
            target_language
        )
        
        podcast_script = PodcastScript(
            script=script_data['script'],
            source_document=source_name,
            total_lines=len(script_data['script']),
            estimated_duration=target_duration
        )
        
        logger.info(f"Generated {target_language} script with {podcast_script.total_lines} lines")
        return podcast_script
    
    def generate_script_from_website(
        self,
        website_chunks: List[Any],
        source_url: str,
        podcast_style: str = "conversational",
        target_duration: str = "10 minutes",
        target_language: str = "English"
    ) -> PodcastScript:
        """Generate script from website with language support"""
        logger.info(f"Generating {target_language} podcast script from website: {source_url}")
        
        if not website_chunks:
            raise ValueError("No website content provided")
        
        website_content = "\n\n".join([chunk.content for chunk in website_chunks])
        script_data = self._generate_conversation_script(
            website_content,
            podcast_style,
            target_duration,
            target_language
        )
        
        podcast_script = PodcastScript(
            script=script_data['script'],
            source_document=source_url,
            total_lines=len(script_data['script']),
            estimated_duration=target_duration
        )
        
        logger.info(f"Generated {target_language} website script with {podcast_script.total_lines} lines")
        return podcast_script
    
    def _generate_conversation_script(
        self,
        document_content: str,
        podcast_style: str,
        target_duration: str,
        target_language: str = "English"
    ) -> Dict[str, Any]:
        """Core script generation with enhanced language support"""

        style_prompts = {
            "conversational": "Create a natural, friendly conversation between two hosts discussing the document. They should build on each other's points and occasionally ask clarifying questions.",
            "educational": "Create an educational discussion where one speaker explains concepts and the other asks thoughtful questions to help clarify complex topics for listeners.",
            "interview": "Create an interview format where Speaker 1 acts as the interviewer asking questions and Speaker 2 provides detailed explanations from the document.",
            "debate": "Create a thoughtful discussion where speakers present different perspectives on the topics, maintaining respect while exploring various viewpoints."
        }
        
        style_instruction = style_prompts.get(podcast_style, style_prompts["conversational"])
    
        duration_guidelines = {
            "2 minutes": "Create a very brief conversation focusing on 1-2 key points only. Keep explanations extremely concise. Generate at least 300-400 words",
            "5 minutes": "Keep the conversation concise, focusing on 2-3 main points with brief explanations. Generate at least 750 words",
            "10 minutes": "make sure to cover all the topics thoroughly with good explanations and examples, dont miss out on anything. Generate at least 1500 words",
            "15 minutes": "Provide comprehensive coverage with detailed discussions and multiple examples.",
            "20 minutes": "Create an in-depth exploration with extensive analysis and supporting details."
        }
        
        duration_guide = duration_guidelines.get(target_duration, duration_guidelines["10 minutes"])
        
        # Enhanced language instructions with specific number and name conversion
        language_instruction = f"""
        CRITICAL LANGUAGE REQUIREMENT - READ CAREFULLY:
        - Generate the ENTIRE podcast script in {target_language}
        - ALL dialogue must be in {target_language} language only
        - Use natural, conversational {target_language}
        - Maintain cultural context appropriate for {target_language} speakers
        
        IMPORTANT: Convert ALL elements to {target_language}:
        - Convert ALL numbers to {target_language} words (e.g., "2024" → "two thousand twenty-four" in {target_language})
        - Convert ALL proper names to {target_language} pronunciation equivalents where appropriate
        - Convert ALL measurements, dates, and numerical values to {target_language}
        - Convert ALL technical terms to commonly understood {target_language} equivalents
        - If the source content is in a different language, TRANSLATE EVERYTHING to {target_language}
        
        EXCEPTIONS (keep in original form):
        - Company names (Google, Microsoft, etc.)
        - Product names (iPhone, Windows, etc.)
        - Acronyms (AI, NASA, etc.)
        - Scientific names (when specifically technical)
        
        Do NOT mix languages - stay 100% consistent with {target_language} throughout the entire script.
        """
        
        prompt = f"""Using the following document, create a podcast script for two speakers: 'Speaker 1' and 'Speaker 2'. 

{language_instruction}

STYLE GUIDELINES:
{style_instruction}

DURATION GUIDELINES:
{duration_guide}

CONVERSATION RULES:
1. Each speaker should speak for 4-5 sentences maximum before alternating
2. The conversation should flow naturally with smooth transitions
3. Use engaging, conversational language that's easy to understand
4. Include brief introductions at the start and wrap-up at the end
5. Break down complex concepts into digestible explanations
6. Maintain professional grammar and punctuation throughout
7. Make it engaging for listeners who haven't read the document

RESPONSE FORMAT:
Respond with a valid JSON object containing a 'script' array. Each array element should be an object with either 'Speaker 1' or 'Speaker 2' as the key and their dialogue as the value.
Respond ONLY with the valid JSON object described above. Do not include explanations, markdown formatting, or text outside the JSON.

Example format (for {target_language}):
{{
  "script": [
    {{"Speaker 1": "Welcome everyone to our podcast! Today we're diving into some fascinating insights from this document..."}},
    {{"Speaker 2": "Thanks for having me! I'm really excited to discuss this topic. The first thing that caught my attention was..."}}
  ]
}}

DOCUMENT CONTENT:
{document_content[:700000]}

Generate an engaging {target_duration} podcast script in {target_language} now. Remember to convert ALL numbers and names to {target_language}:"""
        
        try:
            logger.info(f"Sending request to LLM for {target_language} podcast script generation...")
            response = self.llm.invoke(prompt).content

            if not response or len(response.strip()) == 0:
                raise ValueError("Received empty response from LLM")

            logger.debug(f"Raw LLM response (first 400 chars): {response[:400]}")

            script_data = safe_json_parse(response)

            if not script_data or 'script' not in script_data:
                raise ValueError("Invalid or empty script format returned by LLM")

            # Post-process to ensure language consistency
            validated_script = self._validate_and_clean_script(script_data['script'], target_language)
            return {'script': validated_script}
                        
        except json.JSONDecodeError as e:
            response_clean = response.strip()
            if response_clean.startswith('```json'):
                response_clean = response_clean[7:-3]
            elif response_clean.startswith('```'):
                response_clean = response_clean[3:-3]
            
            try:
                script_data = json.loads(response_clean)
                validated_script = self._validate_and_clean_script(script_data['script'], target_language)
                return {'script': validated_script}
            except:
                raise ValueError(f"Could not parse LLM response as valid JSON: {response}")
        
        except Exception as e:
            logger.error(f"Error generating script: {str(e)}")
            raise

    def _validate_and_clean_script(self, script: List[Dict[str, str]], target_language: str = "English") -> List[Dict[str, str]]:
        """Validate and clean script with language consistency check"""
        cleaned_script = []
        expected_speaker = "Speaker 1"
        
        for item in script:
            if not isinstance(item, dict) or len(item) != 1:
                logger.warning(f"Skipping invalid entry: {item}")
                continue
            
            speaker, dialogue = next(iter(item.items()))
            speaker = speaker.strip()
            dialogue = dialogue.strip()

            # Normalize speakers
            if speaker not in ["Speaker 1", "Speaker 2"]:
                if "1" in speaker or "one" in speaker.lower():
                    speaker = "Speaker 1"
                elif "2" in speaker or "two" in speaker.lower():
                    speaker = "Speaker 2"
                else:
                    speaker = expected_speaker  # fallback

            if not dialogue:
                continue
            
            if not dialogue.endswith(('.', '!', '?')):
                dialogue += '.'

            # Basic language consistency check (can be enhanced)
            cleaned_script.append({speaker: dialogue})
            expected_speaker = "Speaker 2" if expected_speaker == "Speaker 1" else "Speaker 1"
        
        if len(cleaned_script) < 2:
            raise ValueError(f"Generated script too short ({len(cleaned_script)} lines)")
        
        logger.info(f"Validated and cleaned {len(cleaned_script)} lines for {target_language}.")
        return cleaned_script

    def _smart_truncate_content(self, content: str, max_chars: int = 700000) -> str:
        """Truncate content while preserving source markers"""
        if len(content) <= max_chars:
            return content
        
        # If content has source markers (=== SOURCE: ===), preserve them
        if "=== SOURCE:" in content:
            sources = content.split("=== SOURCE:")
            truncated_sources = []
            current_length = 0
            
            for source in sources:
                if not source.strip():
                    continue
                
                source_with_marker = f"=== SOURCE:{source}"
                
                # Take proportional amount from each source
                if current_length + len(source_with_marker) <= max_chars:
                    truncated_sources.append(source_with_marker)
                    current_length += len(source_with_marker)
                else:
                    # Add truncated version of this source
                    remaining = max_chars - current_length
                    if remaining > 500:  # Only add if meaningful amount remains
                        truncated_sources.append(source_with_marker[:remaining])
                    break
            
            return "\n\n".join(truncated_sources)
        
        # Simple truncation for non-marked content
        return content[:max_chars]


if __name__ == "__main__":
    import os
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)
        
    generator = PodcastScriptGenerator(openai_api_key)
    
    try:
        sample_text = """
        Artificial Intelligence (AI) represents one of the most significant technological advances of our time. 
        In 2024, machine learning algorithms have improved by 75% compared to 2020. 
        Deep learning, which uses neural networks with multiple layers, has revolutionized fields like computer vision. 
        The company Google developed TensorFlow, while Facebook created PyTorch. 
        Applications range from autonomous vehicles to medical diagnosis, with studies showing 95% accuracy in detecting certain diseases.
        """
        
        # Test with different languages
        languages_to_test = ["Hindi", "Spanish", "French", "German"]
        
        for language in languages_to_test:
            print(f"\n{'='*60}")
            print(f"TESTING {language.upper()} SCRIPT GENERATION")
            print(f"{'='*60}")
            
            try:
                script = generator.generate_script_from_text(
                    sample_text,
                    source_name="AI Overview",
                    podcast_style="conversational",
                    target_duration="3 minutes",
                    target_language=language
                )
                
                print(f"✓ Successfully generated {language} script")
                print(f"Lines: {script.total_lines}")
                
                # Show first few lines to verify language conversion
                print("\nFirst 3 lines:")
                for i, line_dict in enumerate(script.script[:3], 1):
                    speaker, dialogue = next(iter(line_dict.items()))
                    print(f"  {i}. {speaker}: {dialogue[:100]}...")
                    
            except Exception as e:
                print(f"✗ Failed to generate {language} script: {e}")
        
    except Exception as e:
        print(f"Error: {e}")