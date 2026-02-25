import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import File, Task, User
from app.schemas import FileResponse
from app.auth import get_current_user
from app.config import settings
from app.storage import upload_file_to_s3, get_file_from_s3, delete_file_from_s3
import io

router = APIRouter(prefix="/api/tasks/{task_id}/files", tags=["Files"])


@router.post("", response_model=list[FileResponse], status_code=status.HTTP_201_CREATED)
async def upload_files(
    task_id: uuid.UUID,
    files: List[UploadFile] = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.is_deleted == False))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    uploaded = []
    for file in files:
        if file.content_type not in settings.allowed_file_types_list:
            raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed")

        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds maximum size of {settings.MAX_FILE_SIZE} bytes")

        s3_key = await upload_file_to_s3(content, file.filename, file.content_type)

        db_file = File(
            filename=s3_key.split("/")[-1],
            original_filename=file.filename,
            content_type=file.content_type,
            size=len(content),
            s3_key=s3_key,
            task_id=task_id,
            uploaded_by=current_user.id,
        )
        db.add(db_file)
        await db.flush()
        await db.refresh(db_file)
        uploaded.append(db_file)

    return [FileResponse.model_validate(f) for f in uploaded]


@router.get("", response_model=list[FileResponse])
async def list_files(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(File).where(File.task_id == task_id).order_by(File.created_at.desc()))
    return [FileResponse.model_validate(f) for f in result.scalars().all()]


@router.get("/{file_id}")
async def download_file(task_id: uuid.UUID, file_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(File).where(File.id == file_id, File.task_id == task_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    content = await get_file_from_s3(file.s3_key)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=file.content_type,
        headers={"Content-Disposition": f'attachment; filename="{file.original_filename}"'},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(task_id: uuid.UUID, file_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(File).where(File.id == file_id, File.task_id == task_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    await delete_file_from_s3(file.s3_key)
    await db.delete(file)
    await db.flush()
