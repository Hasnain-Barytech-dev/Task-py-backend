# TaskHub — Backend API

Hey there! This is the backend for **TaskHub**, a task management system I built using **FastAPI** and **Python**. It handles everything from user authentication to real-time WebSocket updates, file storage, analytics, and background jobs. Basically, this is the brain behind the whole operation.

---

## What's Under the Hood

Here's a quick rundown of what this backend actually does:

- **User Authentication** — Register, login, and profile management using JWT tokens. Passwords are hashed with bcrypt, so nothing gets stored in plain text.
- **Task Management** — Full CRUD operations on tasks with soft-delete (nothing is truly gone), bulk-create support, and filtering/search/sort/pagination out of the box.
- **Comments** — Users can leave comments on tasks. Comments support Markdown formatting (rendered server-side) and are sanitized with `bleach` to prevent XSS attacks.
- **File Attachments** — Upload, download, and delete files attached to tasks. Files go to AWS S3 (or any S3-compatible storage like Google Cloud Storage). There's file type and size validation baked in (max 10MB by default).
- **Analytics** — Get task overviews, user performance metrics, trend data over time, and even export everything to an Excel spreadsheet.
- **Real-time Updates** — WebSocket endpoint that broadcasts task and comment events to all connected users. The frontend uses this for live updates without polling.
- **Caching** — Redis caching layer with a 5-minute TTL for tasks and analytics. Cache gets automatically invalidated when data changes.
- **Background Jobs** — Celery workers handle email notifications and check for overdue tasks every 5 minutes. Celery Beat runs the scheduler.
- **Notifications** — In-app notifications for task assignments, overdue alerts, and new comments. Optionally sends email notifications too.
- **Rate Limiting** — 100 requests per minute per IP using `slowapi`, so nobody can hammer the API.
- **API Docs** — FastAPI auto-generates interactive Swagger UI at `/docs` and ReDoc at `/redoc`. No extra setup needed.

---

## Tech Stack

| What              | Technology                                      |
|-------------------|-------------------------------------------------|
| Framework         | FastAPI 0.115                                   |
| ORM               | SQLAlchemy 2.0 (fully async with `asyncpg`)     |
| Database          | PostgreSQL 14+                                  |
| Auth              | JWT via `python-jose`, passwords via `passlib`   |
| Caching           | Redis 5+ (async via `redis-py`)                 |
| File Storage      | AWS S3 / GCS (via `boto3`)                      |
| Background Tasks  | Celery 5.4 with Redis as broker                 |
| Email             | SMTP (Gmail by default)                         |
| Markdown          | `markdown` + `bleach` for rendering & sanitizing |
| Excel Export      | `openpyxl`                                      |
| Rate Limiting     | `slowapi`                                       |
| Server            | Uvicorn (ASGI)                                  |

---

## Getting Started

### Prerequisites

You'll need **Python 3.12+** installed. You'll also need access to:
- A **PostgreSQL** database (14+ recommended)
- A **Redis** instance (for caching and Celery)
- An **AWS S3 bucket** or S3-compatible storage (for file uploads)

### 1. Set Up the Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy or edit the `.env` file in the backend root. Here's what each variable does:

| Variable                  | What It Does                                                    | Default                               |
|---------------------------|-----------------------------------------------------------------|---------------------------------------|
| `APP_NAME`                | Application name shown in API docs                              | `TaskHub`                             |
| `APP_VERSION`             | App version shown in API docs                                   | `1.0.0`                               |
| `DEBUG`                   | Enables SQLAlchemy query logging                                | `false`                               |
| `SECRET_KEY`              | JWT signing secret — **change this in production!**             | `change-me`                           |
| `ALGORITHM`               | JWT algorithm                                                   | `HS256`                               |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry (1440 = 24 hours)                             | `1440`                                |
| `DB_HOST`                 | PostgreSQL host                                                 | `localhost`                           |
| `DB_PORT`                 | PostgreSQL port                                                 | `5432`                                |
| `DB_NAME`                 | Database name                                                   | `full_stack`                          |
| `DB_USER`                 | Database user                                                   | `postgres`                            |
| `DB_PASSWORD`             | Database password                                               | `newpassword`                         |
| `REDIS_HOST`              | Redis host                                                      | `localhost`                           |
| `REDIS_PORT`              | Redis port                                                      | `6379`                                |
| `REDIS_DB`                | Redis database number                                           | `0`                                   |
| `REDIS_USER`              | Redis username (leave blank if none)                            | ` `                                   |
| `REDIS_PASSWORD`          | Redis password (leave blank if none)                            | ` `                                   |
| `AWS_ACCESS_KEY_ID`       | S3 access key                                                   | ` `                                   |
| `AWS_SECRET_ACCESS_KEY`   | S3 secret key                                                   | ` `                                   |
| `AWS_BUCKET`              | S3 bucket name                                                  | ` `                                   |
| `AWS_REGION`              | S3 region                                                       | ` `                                   |
| `CUSTOM_S3_ENDPOINT_URL`  | Custom S3 endpoint (for GCS, MinIO, etc.)                       | ` `                                   |
| `CORS_ORIGINS`            | Comma-separated allowed origins                                 | `http://localhost:5173`               |
| `SMTP_HOST`               | SMTP server                                                     | `smtp.gmail.com`                      |
| `SMTP_PORT`               | SMTP port                                                       | `587`                                 |
| `SMTP_USER`               | SMTP username/email                                             | ` `                                   |
| `SMTP_PASSWORD`           | SMTP app password                                               | ` `                                   |
| `EMAIL_FROM`              | "From" address for outgoing emails                              | `noreply@taskhub.com`                 |
| `MAX_FILE_SIZE`           | Max upload size in bytes (10MB default)                         | `10485760`                            |
| `ALLOWED_FILE_TYPES`      | Comma-separated MIME types allowed for upload                   | `image/png,image/jpeg,...`            |

### 4. Run the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. Check `http://localhost:8000/docs` for the interactive API docs.

### 5. Start the Celery Worker (Optional)

If you want background email notifications and automated overdue task checks:

```bash
# In a separate terminal
celery -A app.celery_worker.celery_app worker --loglevel=info

# And for the scheduler (checks overdue tasks every 5 min)
celery -A app.celery_worker.celery_app beat --loglevel=info
```

---

## Running with Docker

There's a `Dockerfile` included that builds a slim Python 3.12 image:

```bash
docker build -t taskhub-backend .
docker run -p 8000:8000 --env-file .env taskhub-backend
```

Or if you want the full stack (backend + frontend + Postgres + Redis + Celery), use the `docker-compose.yml` in the project root:

```bash
# From the project root (one level up)
docker-compose up --build
```

This spins up:
- **PostgreSQL 16** on port 5433
- **Redis 7** on port 6379
- **Backend API** on port 8000
- **Celery Worker** for async tasks
- **Celery Beat** for periodic scheduling
- **Frontend** on port 80

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, middleware, lifespan, WebSocket
│   ├── config.py            # Pydantic Settings loaded from .env
│   ├── database.py          # Async SQLAlchemy engine + session factory
│   ├── models.py            # SQLAlchemy models (User, Task, Comment, File, Tag, Notification)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── auth.py              # JWT creation, password hashing, auth dependency
│   ├── cache.py             # Redis cache helpers (get, set, delete, pattern delete)
│   ├── storage.py           # AWS S3 upload/download/delete/presigned URL
│   ├── websocket.py         # WebSocket connection manager
│   ├── celery_worker.py     # Celery tasks (email, overdue check)
│   └── routes/
│       ├── __init__.py
│       ├── auth.py          # /api/auth/* — register, login, profile, list users
│       ├── tasks.py         # /api/tasks/* — CRUD, bulk create, list with filters
│       ├── comments.py      # /api/tasks/{id}/comments/* — CRUD
│       ├── files.py         # /api/tasks/{id}/files/* — upload, list, download, delete
│       ├── analytics.py     # /api/analytics/* — overview, performance, trends, export
│       └── notifications.py # /api/notifications/* — list, mark read
├── Dockerfile               # Python 3.12-slim image
├── render.yaml              # Render deployment blueprint
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables (not committed in production)
```

---

## API Endpoints

### Authentication

| Method | Endpoint              | Description                     | Auth Required |
|--------|-----------------------|---------------------------------|---------------|
| POST   | `/api/auth/register`  | Register a new user             | No            |
| POST   | `/api/auth/login`     | Login, returns JWT + user data  | No            |
| GET    | `/api/auth/me`        | Get current user's profile      | Yes           |
| PUT    | `/api/auth/me`        | Update name or avatar           | Yes           |
| GET    | `/api/auth/users`     | List all registered users       | Yes           |

### Tasks

| Method | Endpoint              | Description                                         | Auth Required |
|--------|-----------------------|-----------------------------------------------------|---------------|
| POST   | `/api/tasks`          | Create a new task                                   | Yes           |
| POST   | `/api/tasks/bulk`     | Bulk create multiple tasks at once                  | Yes           |
| GET    | `/api/tasks`          | List tasks (supports search, filter, sort, paginate)| Yes           |
| GET    | `/api/tasks/{id}`     | Get a single task with comments, files, and tags    | Yes           |
| PUT    | `/api/tasks/{id}`     | Update task fields                                  | Yes           |
| DELETE | `/api/tasks/{id}`     | Soft-delete a task                                  | Yes           |

### Comments

| Method | Endpoint                               | Description         | Auth Required |
|--------|----------------------------------------|---------------------|---------------|
| POST   | `/api/tasks/{id}/comments`             | Add a comment       | Yes           |
| GET    | `/api/tasks/{id}/comments`             | List comments       | Yes           |
| PUT    | `/api/tasks/{id}/comments/{comment_id}`| Update a comment    | Yes           |
| DELETE | `/api/tasks/{id}/comments/{comment_id}`| Delete a comment    | Yes           |

### File Attachments

| Method | Endpoint                            | Description         | Auth Required |
|--------|-------------------------------------|---------------------|---------------|
| POST   | `/api/tasks/{id}/files`             | Upload file(s)      | Yes           |
| GET    | `/api/tasks/{id}/files`             | List files          | Yes           |
| GET    | `/api/tasks/{id}/files/{file_id}`   | Download a file     | Yes           |
| DELETE | `/api/tasks/{id}/files/{file_id}`   | Delete a file       | Yes           |

### Analytics

| Method | Endpoint                      | Description                                 | Auth Required |
|--------|-------------------------------|---------------------------------------------|---------------|
| GET    | `/api/analytics/overview`     | Task counts by status and priority          | Yes           |
| GET    | `/api/analytics/performance`  | Per-user task completion rates              | Yes           |
| GET    | `/api/analytics/trends`       | Tasks created vs completed over time        | Yes           |
| GET    | `/api/analytics/export`       | Export all tasks as an Excel (.xlsx) file    | Yes           |

### Notifications

| Method | Endpoint                             | Description                | Auth Required |
|--------|--------------------------------------|----------------------------|---------------|
| GET    | `/api/notifications/`                | List user's notifications  | Yes           |
| PUT    | `/api/notifications/{id}/read`       | Mark notification as read  | Yes           |

### WebSocket

| Protocol | Endpoint        | Description                            |
|----------|-----------------|----------------------------------------|
| WS       | `/ws/{token}`   | Real-time task/comment event broadcast |

### Health Check

| Method | Endpoint       | Description              |
|--------|----------------|--------------------------|
| GET    | `/api/health`  | Returns app name/version |

---

## Database Models

The app uses **6 models** with PostgreSQL UUIDs as primary keys:

- **User** — `email`, `username`, `full_name`, `hashed_password`, `avatar_url`, `is_active`
- **Task** — `title`, `description`, `status` (todo/in_progress/completed/overdue), `priority` (low/medium/high/urgent), `due_date`, `notify_overdue`, `is_deleted`, foreign keys to creator and assignee
- **Comment** — `content` (raw Markdown), `content_html` (rendered), linked to task and user
- **File** — `filename`, `original_filename`, `content_type`, `size`, `s3_key`, linked to task and uploader
- **Tag** — `name`, `color` (hex), many-to-many with tasks via `task_tags` association table
- **Notification** — `type` (task_overdue/task_assigned/comment_added), `title`, `message`, `is_read`, linked to user and task

Composite indexes are set on commonly queried columns like `(status, priority)`, `(created_by, status)`, and `(assigned_to, status)` for fast filtering.

---

## How Things Work Together

1. **On startup**, the app initializes the database (creates tables if they don't exist) and auto-transitions overdue tasks.
2. **Requests flow** through CORS middleware → rate limiter → route handlers → async database sessions.
3. **Cache** sits in front of task lists and analytics. When a task is created/updated/deleted, relevant cache keys are invalidated.
4. **WebSocket** events are broadcasted whenever tasks or comments are created, updated, or deleted. Connected clients get live data.
5. **Celery Beat** runs a periodic check every 5 minutes to mark overdue tasks and send notifications/emails.
6. **File uploads** go directly to S3. The database stores metadata (filename, size, type, S3 key), not the actual file bytes.

---

## Deployment

### Deploying to Render

This project includes a `render.yaml` blueprint that sets up everything on [Render](https://render.com):

1. **Push** this backend folder to a GitHub repo.
2. Go to [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**.
3. Connect your repo and Render will auto-detect the `render.yaml`.
4. It creates:
   - A **PostgreSQL database** (free tier)
   - A **Web Service** running the FastAPI app
5. Set the following environment variables manually in the Render dashboard:
   - `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` — for email notifications
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_BUCKET`, `AWS_REGION` — for file uploads
   - `CUSTOM_S3_ENDPOINT_URL` — if using GCS or another S3-compatible provider
   - `CORS_ORIGINS` — set to your frontend's URL (e.g., `https://your-app.vercel.app`)
6. Render auto-generates `SECRET_KEY` and wires up all database credentials.

The backend is currently live at: `https://task-py-backend.onrender.com`

### Deploying with Docker

```bash
docker build -t taskhub-backend .
docker run -p 8000:8000 \
  -e DB_HOST=your-db-host \
  -e DB_PORT=5432 \
  -e DB_NAME=taskhub \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your-password \
  -e REDIS_HOST=your-redis-host \
  -e SECRET_KEY=your-secret-key \
  taskhub-backend
```

### Deploying with Docker Compose (Full Stack)

From the project root:

```bash
docker-compose up --build -d
```

This brings up the entire stack — Postgres, Redis, backend API, Celery worker, Celery beat, and the frontend. The backend will be available on port 8000.

---

## A Few Things to Keep in Mind

- **Database tables are auto-created** on startup via SQLAlchemy's `create_all`. No need to run migrations manually (though if you modify models, consider adding Alembic migrations).
- **JWT tokens** are stored in `localStorage` on the frontend side. For production, you might want to switch to httpOnly cookies.
- **File uploads** require valid S3/GCS credentials. Without them, file operations will fail.
- **Email notifications** need SMTP credentials configured. If they're missing, Celery tasks will skip sending emails silently.
- **Redis is optional** for running the API itself — if Redis is down, caching fails gracefully. But Celery requires Redis as its broker.
- **Rate limiting** is set at 100 requests/minute per IP. You can adjust the limiter in `main.py`.

---

## Testing the API

Once the server is running, the easiest way to test is through the Swagger UI:

```
http://localhost:8000/docs
```

Or register a user via cURL:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "full_name": "Test User",
    "password": "password123"
  }'
```

Then login to get a JWT token and use it in the `Authorization: Bearer <token>` header for all other endpoints.
