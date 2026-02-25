from celery import Celery
from app.config import settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

celery_app = Celery("taskhub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "check-overdue-tasks": {
            "task": "app.celery_worker.process_task_overdue_check",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)


@celery_app.task
def send_email_notification(to_email: str, subject: str, body: str):
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return {"status": "skipped", "reason": "SMTP credentials not configured"}

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@celery_app.task
def process_task_overdue_check():
    """Check for tasks past due date and mark them overdue. For tasks with notify_overdue=True,
    create in-app notification and dispatch email."""
    import datetime
    from sqlalchemy import create_engine, select, update
    from sqlalchemy.orm import Session

    # Build sync DB URL from settings
    sync_url = f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    engine = create_engine(sync_url)

    from app.models import Task, TaskStatus, Notification, NotificationType, User

    with Session(engine) as session:
        now = datetime.datetime.now(datetime.timezone.utc)

        # Find tasks that are past due_date and not already completed/overdue/deleted
        overdue_tasks = session.execute(
            select(Task).where(
                Task.due_date < now,
                Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.OVERDUE]),
                Task.is_deleted == False,
            )
        ).scalars().all()

        marked = 0
        notified = 0

        for task in overdue_tasks:
            task.status = TaskStatus.OVERDUE
            marked += 1

            if task.notify_overdue:
                notify_user_id = task.assigned_to or task.created_by
                notification = Notification(
                    user_id=notify_user_id,
                    task_id=task.id,
                    type=NotificationType.TASK_OVERDUE,
                    title=f"Task Overdue: {task.title}",
                    message=f"Task '{task.title}' is past its due date. Please take action.",
                )
                session.add(notification)
                notified += 1

                # Send email if assignee exists
                if task.assigned_to:
                    assignee = session.get(User, task.assigned_to)
                    if assignee:
                        send_email_notification.delay(
                            assignee.email,
                            f"Overdue: {task.title}",
                            f"<p>Task <strong>{task.title}</strong> is overdue. Please update its status.</p>",
                        )

        session.commit()

    engine.dispose()
    return {"status": "processed", "marked_overdue": marked, "notifications_sent": notified}
