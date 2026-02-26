import uuid
import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(default="#3B82F6", pattern=r"^#[0-9a-fA-F]{6}$")


class TagResponse(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[str] = "medium"
    start_date: Optional[datetime.datetime] = None
    due_date: Optional[datetime.datetime] = None
    assigned_to: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = []
    notify_overdue: Optional[bool] = False


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[datetime.datetime] = None
    due_date: Optional[datetime.datetime] = None
    assigned_to: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    notify_overdue: Optional[bool] = None


class TaskBulkCreate(BaseModel):
    tasks: List[TaskCreate]


class FileResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    content_type: str
    size: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class CommentBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class CommentCreate(CommentBase):
    pass


class CommentUpdate(CommentBase):
    pass


class CommentResponse(BaseModel):
    id: uuid.UUID
    content: str
    content_html: Optional[str] = None
    task_id: uuid.UUID
    user_id: uuid.UUID
    author: Optional[UserResponse] = None
    is_deleted: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    start_date: Optional[datetime.datetime] = None
    due_date: Optional[datetime.datetime] = None
    notify_overdue: bool = False
    is_deleted: bool
    created_by: uuid.UUID
    assigned_to: Optional[uuid.UUID] = None
    creator: Optional[UserResponse] = None
    assignee: Optional[UserResponse] = None
    tags: List[TagResponse] = []
    files: List[FileResponse] = []
    comments: List[CommentResponse] = []
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TaskOverview(BaseModel):
    total_tasks: int
    completed: int
    in_progress: int
    todo: int
    overdue: int
    by_priority: dict
    by_status: dict


class UserPerformance(BaseModel):
    user_id: uuid.UUID
    username: str
    full_name: str
    total_assigned: int
    completed: int
    in_progress: int
    completion_rate: float


class TaskTrend(BaseModel):
    date: str
    created: int
    completed: int


class WebSocketMessage(BaseModel):
    type: str
    data: dict


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    unread_count: int

