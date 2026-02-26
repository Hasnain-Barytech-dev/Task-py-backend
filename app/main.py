from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.database import init_db
from app.cache import close_redis
from app.websocket import manager
from app.auth import get_current_user
from app.routes import auth, tasks, comments, files, analytics, notifications
from jose import jwt


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Auto-transition task statuses on startup
    try:
        from app.database import async_session
        from app.models import Task, TaskStatus, Notification, NotificationType, User
        from sqlalchemy import update, select
        from datetime import datetime, timezone
        from app.celery_worker import send_email_notification

        async with async_session() as session:
            now = datetime.now(timezone.utc)

            # 1) Mark past-due tasks as OVERDUE + create notifications
            overdue_result = await session.execute(
                select(Task)
                .where(Task.due_date < now, Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.OVERDUE]), Task.is_deleted == False)
            )
            overdue_tasks = overdue_result.scalars().all()
            for task in overdue_tasks:
                task.status = TaskStatus.OVERDUE
                if task.notify_overdue:
                    notify_user_id = task.assigned_to or task.created_by
                    notif = Notification(
                        user_id=notify_user_id,
                        task_id=task.id,
                        type=NotificationType.TASK_OVERDUE,
                        title=f"Task Overdue: {task.title}",
                        message=f"Task '{task.title}' is past its due date. Please take action.",
                    )
                    session.add(notif)
                    # Send email
                    try:
                        user_result = await session.execute(select(User).where(User.id == notify_user_id))
                        u = user_result.scalar_one_or_none()
                        if u and u.email:
                            send_email_notification(
                                u.email,
                                f"Overdue: {task.title}",
                                f"<p>Task <strong>{task.title}</strong> is overdue. Please update its status.</p>",
                            )
                    except Exception:
                        pass

            # 2) Mark TODO tasks where start_date has passed as IN_PROGRESS
            await session.execute(
                update(Task)
                .where(Task.start_date <= now, Task.status == TaskStatus.TODO, Task.is_deleted == False)
                .values(status=TaskStatus.IN_PROGRESS)
            )

            await session.commit()
    except Exception:
        pass  # Don't block startup
    yield
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A comprehensive task management system with real-time collaboration",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(files.router)
app.include_router(analytics.router)
app.include_router(notifications.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
