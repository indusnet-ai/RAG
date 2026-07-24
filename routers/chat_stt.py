from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
import uuid, os, shutil, logging

from routers.dependencies import get_current_user
from services.stt import SpeechToTextService
# ADD THIS after line 4 (after existing imports)
from services.metrics import track_stt_request, track_stt_failure
import time

router = APIRouter(tags=["Speech-to-Text"])

logger = logging.getLogger(__name__)


class ChatSTTResponse(BaseModel):
    text: str


@router.post("/chat/stt", response_model=ChatSTTResponse)
async def chat_stt(
    audio: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    """
    Real-time STT endpoint for chat microphone input.
    Optimized for short audio clips (1–10s).
    """
    start_time = time.time()
    # temp storage
    os.makedirs("tmp_chat_audio", exist_ok=True)
    ext = os.path.splitext(audio.filename)[-1] or ".wav"
    temp_path = f"tmp_chat_audio/{uuid.uuid4()}{ext}"

    # save file quickly
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)
    except Exception as e:
        logger.error(f"Failed saving audio: {e}")
        raise HTTPException(500, "Unable to read uploaded audio")

    # STT
    try:
        stt = SpeechToTextService()
        text = stt.transcribe(temp_path)
        duration = time.time() - start_time  # ✅ ADD THIS LINE
        track_stt_request(duration)  # ✅ ADD THIS LINE
    except Exception as e:
        logger.error(f"STT error: {e}")
        raise HTTPException(500, "Speech transcription failed")

    # cleanup
    try: os.remove(temp_path)
    except: pass

    if not text:
        raise HTTPException(400, "No speech detected")

    return ChatSTTResponse(text=text)
