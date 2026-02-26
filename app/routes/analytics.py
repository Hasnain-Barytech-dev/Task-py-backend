import json
import io
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_, extract
from app.database import get_db
from app.models import Task, User, TaskStatus, TaskPriority
from app.schemas import TaskOverview, UserPerformance, TaskTrend
from app.auth import get_current_user
from app.cache import cache_get, cache_set
from openpyxl import Workbook

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/overview", response_model=TaskOverview)
async def get_overview(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    cached = await cache_get(f"analytics:overview:{current_user.id}")
    if cached:
        return TaskOverview.model_validate_json(cached)

    now = datetime.now(timezone.utc)

    # Real-time status transitions before counting
    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(Task)
        .where(Task.due_date < now, Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.OVERDUE]), Task.is_deleted == False)
        .values(status=TaskStatus.OVERDUE)
    )
    await db.execute(
        sql_update(Task)
        .where(Task.start_date <= now, Task.status == TaskStatus.TODO, Task.is_deleted == False)
        .values(status=TaskStatus.IN_PROGRESS)
    )
    await db.flush()

    base = select(Task).where(Task.is_deleted == False)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    completed = (await db.execute(select(func.count()).select_from(base.where(Task.status == TaskStatus.COMPLETED).subquery()))).scalar()
    in_progress = (await db.execute(select(func.count()).select_from(base.where(Task.status == TaskStatus.IN_PROGRESS).subquery()))).scalar()
    todo = (await db.execute(select(func.count()).select_from(base.where(Task.status == TaskStatus.TODO).subquery()))).scalar()
    overdue = (await db.execute(select(func.count()).select_from(
        base.where(Task.status == TaskStatus.OVERDUE).subquery()
    ))).scalar()

    by_status = {"todo": todo, "in_progress": in_progress, "completed": completed, "overdue": overdue}

    priority_result = await db.execute(
        select(Task.priority, func.count()).where(Task.is_deleted == False).group_by(Task.priority)
    )
    by_priority = {str(row[0].value): row[1] for row in priority_result.all()}

    overview = TaskOverview(
        total_tasks=total, completed=completed, in_progress=in_progress,
        todo=todo, overdue=overdue, by_priority=by_priority, by_status=by_status,
    )
    await cache_set(f"analytics:overview:{current_user.id}", overview.model_dump_json(), ttl=120)
    return overview


@router.get("/performance", response_model=list[UserPerformance])
async def get_performance(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    cached = await cache_get("analytics:performance")
    if cached:
        return json.loads(cached)

    users_result = await db.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    performances = []
    for user in users:
        base = select(Task).where(Task.assigned_to == user.id, Task.is_deleted == False)
        total_assigned = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
        completed = (await db.execute(select(func.count()).select_from(base.where(Task.status == TaskStatus.COMPLETED).subquery()))).scalar()
        prog = (await db.execute(select(func.count()).select_from(base.where(Task.status == TaskStatus.IN_PROGRESS).subquery()))).scalar()

        performances.append(UserPerformance(
            user_id=user.id, username=user.username, full_name=user.full_name,
            total_assigned=total_assigned, completed=completed, in_progress=prog,
            completion_rate=round((completed / total_assigned * 100), 1) if total_assigned > 0 else 0,
        ))

    await cache_set("analytics:performance", json.dumps([p.model_dump(mode="json") for p in performances]), ttl=120)
    return performances


@router.get("/trends", response_model=list[TaskTrend])
async def get_trends(
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cached = await cache_get(f"analytics:trends:{days}")
    if cached:
        return json.loads(cached)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    created_result = await db.execute(
        select(func.date(Task.created_at).label("d"), func.count().label("c"))
        .where(Task.created_at >= start, Task.is_deleted == False)
        .group_by(func.date(Task.created_at))
        .order_by(func.date(Task.created_at))
    )
    created_map = {str(row.d): row.c for row in created_result.all()}

    completed_result = await db.execute(
        select(func.date(Task.updated_at).label("d"), func.count().label("c"))
        .where(Task.updated_at >= start, Task.status == TaskStatus.COMPLETED, Task.is_deleted == False)
        .group_by(func.date(Task.updated_at))
        .order_by(func.date(Task.updated_at))
    )
    completed_map = {str(row.d): row.c for row in completed_result.all()}

    trends = []
    for i in range(days):
        date_str = str((start + timedelta(days=i)).date())
        trends.append(TaskTrend(date=date_str, created=created_map.get(date_str, 0), completed=completed_map.get(date_str, 0)))

    await cache_set(f"analytics:trends:{days}", json.dumps([t.model_dump() for t in trends]), ttl=120)
    return trends


@router.get("/export")
async def export_tasks(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Task).where(Task.is_deleted == False).order_by(Task.created_at.desc()))
    tasks = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(["ID", "Title", "Description", "Status", "Priority", "Due Date", "Created At"])

    for task in tasks:
        ws.append([
            str(task.id), task.title, task.description or "",
            task.status.value, task.priority.value,
            str(task.due_date) if task.due_date else "",
            str(task.created_at),
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
        headers={"Content-Disposition": "attachment; filename=tasks_export.xlsx"},
    )
