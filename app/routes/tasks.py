import uuid
import json
import math
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc, asc
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Task, Tag, User, Comment, Notification, NotificationType, TaskStatus, TaskPriority, task_tags
from app.schemas import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse, TaskBulkCreate, NotificationResponse
from app.auth import get_current_user
from app.cache import cache_get, cache_set, cache_delete_pattern
from app.websocket import manager
from app.celery_worker import send_email_notification

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


async def get_or_create_tags(db: AsyncSession, tag_names: List[str]) -> List[Tag]:
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        result = await db.execute(select(Tag).where(Tag.name == name))
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            await db.flush()
        tags.append(tag)
    return tags


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    initial_status = TaskStatus(data.status) if data.status else TaskStatus.TODO
    # Auto-transition based on due_date
    if data.due_date:
        now = datetime.now(timezone.utc)
        if data.due_date < now and initial_status not in (TaskStatus.COMPLETED, TaskStatus.OVERDUE):
            initial_status = TaskStatus.OVERDUE
        elif data.due_date >= now and initial_status == TaskStatus.TODO:
            initial_status = TaskStatus.IN_PROGRESS
    task = Task(
        title=data.title,
        description=data.description,
        status=initial_status,
        priority=TaskPriority(data.priority) if data.priority else TaskPriority.MEDIUM,
        due_date=data.due_date,
        notify_overdue=data.notify_overdue or False,
        created_by=current_user.id,
        assigned_to=data.assigned_to,
    )
    if data.tags:
        task.tags = await get_or_create_tags(db, data.tags)
    db.add(task)
    await db.flush()
    await db.refresh(task, ["creator", "assignee", "tags", "files", "comments"])
    await cache_delete_pattern("tasks:*")
    await cache_delete_pattern("analytics:*")

    await manager.broadcast({"type": "task_created", "data": {"task_id": str(task.id), "title": task.title}})

    return TaskResponse.model_validate(task)


@router.post("/bulk", response_model=list[TaskResponse], status_code=status.HTTP_201_CREATED)
async def bulk_create_tasks(data: TaskBulkCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    created = []
    now = datetime.now(timezone.utc)
    for t in data.tasks:
        initial_status = TaskStatus(t.status) if t.status else TaskStatus.TODO
        # Auto-transition based on due_date
        if t.due_date:
            if t.due_date < now and initial_status not in (TaskStatus.COMPLETED, TaskStatus.OVERDUE):
                initial_status = TaskStatus.OVERDUE
            elif t.due_date >= now and initial_status == TaskStatus.TODO:
                initial_status = TaskStatus.IN_PROGRESS
        task = Task(
            title=t.title,
            description=t.description,
            status=initial_status,
            priority=TaskPriority(t.priority) if t.priority else TaskPriority.MEDIUM,
            due_date=t.due_date,
            notify_overdue=t.notify_overdue or False,
            created_by=current_user.id,
            assigned_to=t.assigned_to,
        )
        if t.tags:
            task.tags = await get_or_create_tags(db, t.tags)
        db.add(task)
        await db.flush()
        await db.refresh(task, ["creator", "assignee", "tags", "files", "comments"])
        created.append(task)

    await cache_delete_pattern("tasks:*")
    await cache_delete_pattern("analytics:*")
    return [TaskResponse.model_validate(t) for t in created]


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|due_date|title|priority|status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = f"tasks:{current_user.id}:{page}:{page_size}:{status}:{priority}:{assigned_to}:{search}:{sort_by}:{sort_order}:{tag}"
    cached = await cache_get(cache_key)
    if cached:
        return TaskListResponse.model_validate_json(cached)

    query = select(Task).where(Task.is_deleted == False).options(
        selectinload(Task.creator),
        selectinload(Task.assignee),
        selectinload(Task.tags),
        selectinload(Task.files),
        selectinload(Task.comments).selectinload(Comment.author),
    )

    if status:
        query = query.where(Task.status == TaskStatus(status))
    if priority:
        query = query.where(Task.priority == TaskPriority(priority))
    if assigned_to:
        query = query.where(Task.assigned_to == assigned_to)
    if search:
        query = query.where(or_(Task.title.ilike(f"%{search}%"), Task.description.ilike(f"%{search}%")))
    if tag:
        query = query.join(Task.tags).where(Tag.name == tag.lower())

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    sort_col = getattr(Task, sort_by)
    query = query.order_by(desc(sort_col) if sort_order == "desc" else asc(sort_col))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    tasks = result.unique().scalars().all()
    total_pages = math.ceil(total / page_size) if total else 0

    response = TaskListResponse(
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

    await cache_set(cache_key, response.model_dump_json(), ttl=60)
    return response


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False).options(
            selectinload(Task.creator),
            selectinload(Task.assignee),
            selectinload(Task.tags),
            selectinload(Task.files),
            selectinload(Task.comments),
        )
    )
    task = result.unique().scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: uuid.UUID, data: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.is_deleted == False))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if data.title is not None:
        task.title = data.title
    if data.description is not None:
        task.description = data.description
    if data.status is not None:
        task.status = TaskStatus(data.status)
    if data.priority is not None:
        task.priority = TaskPriority(data.priority)
    if data.due_date is not None:
        task.due_date = data.due_date
    if data.assigned_to is not None:
        task.assigned_to = data.assigned_to
    if data.tags is not None:
        task.tags = await get_or_create_tags(db, data.tags)
    if data.notify_overdue is not None:
        task.notify_overdue = data.notify_overdue

    await db.flush()
    await db.refresh(task, ["creator", "assignee", "tags", "files", "comments"])
    await cache_delete_pattern("tasks:*")
    await cache_delete_pattern("analytics:*")

    await manager.broadcast({"type": "task_updated", "data": {"task_id": str(task.id), "title": task.title}})

    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.is_deleted == False))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.is_deleted = True
    await db.flush()
    await cache_delete_pattern("tasks:*")
    await cache_delete_pattern("analytics:*")

    await manager.broadcast({"type": "task_deleted", "data": {"task_id": str(task.id)}})


@router.post("/{task_id}/notify-overdue", response_model=NotificationResponse)
async def notify_task_overdue(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.assignee), selectinload(Task.creator))
        .where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.OVERDUE:
        raise HTTPException(status_code=400, detail="Task is not overdue")

    # Determine who to notify (assignee or creator)
    notify_user_id = task.assigned_to or task.created_by
    notification = Notification(
        user_id=notify_user_id,
        task_id=task.id,
        type=NotificationType.TASK_OVERDUE,
        title=f"Task Overdue: {task.title}",
        message=f"Task '{task.title}' is past its due date. Please take action.",
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)

    # WebSocket push
    await manager.broadcast({
        "type": "notification",
        "data": {"user_id": str(notify_user_id), "title": notification.title, "task_id": str(task.id)},
    })

    # Email notification (send synchronously so it works without Celery worker)
    recipient = task.assignee or task.creator
    if recipient and recipient.email:
        try:
            send_email_notification(
                recipient.email,
                f"Overdue: {task.title}",
                f"<p>Task <strong>{task.title}</strong> is overdue. Please update its status.</p>",
            )
        except Exception:
            pass  # Don't fail the API call if email fails

    return NotificationResponse.model_validate(notification)

