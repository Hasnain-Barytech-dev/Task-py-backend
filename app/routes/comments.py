import uuid
import markdown as md
import bleach
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Comment, Task, User
from app.schemas import CommentCreate, CommentUpdate, CommentResponse
from app.auth import get_current_user
from app.websocket import manager

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["Comments"])

ALLOWED_TAGS = ["p", "br", "strong", "em", "u", "a", "code", "pre", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "hr"]
ALLOWED_ATTRS = {"a": ["href", "title"]}


def render_markdown(text: str) -> str:
    html = md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


@router.post("", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(task_id: uuid.UUID, data: CommentCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.is_deleted == False))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    comment = Comment(
        content=data.content,
        content_html=render_markdown(data.content),
        task_id=task_id,
        user_id=current_user.id,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment, ["author"])

    await manager.broadcast({
        "type": "comment_added",
        "data": {"task_id": str(task_id), "comment_id": str(comment.id), "author": current_user.full_name}
    })

    return CommentResponse.model_validate(comment)


@router.get("", response_model=list[CommentResponse])
async def list_comments(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Comment)
        .where(Comment.task_id == task_id, Comment.is_deleted == False)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [CommentResponse.model_validate(c) for c in comments]


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(task_id: uuid.UUID, comment_id: uuid.UUID, data: CommentUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.task_id == task_id, Comment.is_deleted == False).options(selectinload(Comment.author))
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    comment.content = data.content
    comment.content_html = render_markdown(data.content)
    await db.flush()
    await db.refresh(comment, ["author"])
    return CommentResponse.model_validate(comment)


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(task_id: uuid.UUID, comment_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Comment).where(Comment.id == comment_id, Comment.task_id == task_id, Comment.is_deleted == False))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    comment.is_deleted = True
    await db.flush()
