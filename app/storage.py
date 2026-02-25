import uuid
import boto3
from botocore.config import Config as BotoConfig
from app.config import settings


def get_s3_client():
    kwargs = dict(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )
    if settings.CUSTOM_S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.CUSTOM_S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


async def upload_file_to_s3(file_content: bytes, original_filename: str, content_type: str) -> str:
    s3 = get_s3_client()
    ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else ""
    key = f"taskhub/files/{uuid.uuid4()}.{ext}" if ext else f"taskhub/files/{uuid.uuid4()}"
    s3.put_object(
        Bucket=settings.AWS_BUCKET,
        Key=key,
        Body=file_content,
        ContentType=content_type,
    )
    return key


async def get_file_from_s3(key: str) -> bytes:
    s3 = get_s3_client()
    response = s3.get_object(Bucket=settings.AWS_BUCKET, Key=key)
    return response["Body"].read()


async def delete_file_from_s3(key: str):
    s3 = get_s3_client()
    s3.delete_object(Bucket=settings.AWS_BUCKET, Key=key)


def generate_presigned_url(key: str, expiration: int = 3600) -> str:
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_BUCKET, "Key": key},
        ExpiresIn=expiration,
    )
