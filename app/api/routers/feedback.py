from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.security import get_current_user_optional
from app.db.session import get_db
from app.core.config import settings

router = APIRouter(prefix=settings.API_V1_STR, tags=["反馈"])


class FeedbackCreate(BaseModel):
    rating: int
    content: str

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int):
        if v < 1 or v > 5:
            raise ValueError("评分必须在 1 到 5 之间")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str):
        if not v:
            raise ValueError("反馈内容不能为空")
        if len(v) > 2000:
            raise ValueError("反馈内容过长")
        return v


@router.post("/feedback")
def submit_feedback(
    payload: FeedbackCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    user_id = getattr(current_user, "id", None) if current_user else None

    rows = db.query(
        """
        INSERT INTO user_feedback (user_id, rating, content)
        VALUES (%s, %s, %s)
        RETURNING id, user_id, rating, content, created_at
        """,
        (user_id, payload.rating, payload.content),
    )

    if not rows:
        raise HTTPException(status_code=500, detail="保存反馈失败")

    row = rows[0]
    return {
        "id": row[0],
        "user_id": row[1],
        "rating": row[2],
        "content": row[3],
        "created_at": row[4],
    }
