"""MinIO (S3-compatible) object storage for rendered videos — replaces serving
media/queue/<id>/video.mp4 straight off local disk, so the app container and the video
files aren't coupled to the same host/volume.

Config comes entirely from env vars (see .env.example): S3_ENDPOINT_URL, S3_ACCESS_KEY,
S3_SECRET_KEY, S3_BUCKET, S3_REGION.
"""
import os

import boto3
from botocore.client import Config

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "antiquary-videos")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

PRESIGNED_URL_TTL_SECONDS = 3600


def _client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name=S3_REGION,
    )


def ensure_bucket() -> None:
    s3 = _client()
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    if S3_BUCKET not in existing:
        s3.create_bucket(Bucket=S3_BUCKET)


def upload_video(local_path: str, object_key: str) -> None:
    _client().upload_file(local_path, S3_BUCKET, object_key, ExtraArgs={"ContentType": "video/mp4"})


def presigned_video_url(object_key: str) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": object_key},
        ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
    )


def delete_video(object_key: str) -> None:
    _client().delete_object(Bucket=S3_BUCKET, Key=object_key)
