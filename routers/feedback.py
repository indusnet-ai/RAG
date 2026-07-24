from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class FeedbackResponse(BaseModel):
    id: UUID
    status: str

from services.feedback_service import (
    create_feedback_service,
    save_screenshot
)
from services.metrics import track_db_connection_failure
from routers.dependencies import get_current_user

router = APIRouter(prefix="/feedback", tags=["Feedback"])
@router.post("/", response_model=FeedbackResponse)
def submit_feedback(
    message: str = Form(...),
    allow_contact: bool = Form(False),
    screenshot: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        def extract_user_id(user):
            if isinstance(user, dict):
                return user.get("id")
            if isinstance(user, (list, tuple)):
                return user[0]
            return getattr(user, "id", None)

        screenshot_path = None
        user_id = extract_user_id(current_user)


        if screenshot:
            screenshot_path = save_screenshot(screenshot)

        feedback_id = create_feedback_service(
            db=db,
            user_id=user_id,
            message=message,
            screenshot_path=screenshot_path,
            allow_contact=allow_contact
        )

        db.commit()

        return {
            "id": feedback_id,
            "status": "Feedback submitted successfully"
        }

    except Exception as e:
        db.rollback()
        track_db_connection_failure()
        raise HTTPException(status_code=500, detail=str(e))
