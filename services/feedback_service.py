import os
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import text

UPLOAD_DIR = "uploads/feedback_screenshots"

os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_screenshot(file) -> str:
    ext = os.path.splitext(file.filename)[-1] or ".png"
    filename = f"{uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    return file_path


def create_feedback_service(
    db: Session,
    user_id: str,
    message: str,
    screenshot_path: str | None,
    allow_contact: bool
):
    feedback_id = str(uuid4())

    db.execute(text("""
        INSERT INTO feedback (
            id, user_id, message, screenshot_path, allow_contact
        ) VALUES (
            :id, :user_id, :message, :screenshot_path, :allow_contact
        )
    """), {
        "id": feedback_id,
        "user_id": user_id,
        "message": message,
        "screenshot_path": screenshot_path,
        "allow_contact": allow_contact
    })

    return feedback_id
