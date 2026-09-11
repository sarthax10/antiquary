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


def get_video_object(object_key: str, range_header: str | None = None) -> dict:
    """Fetches a video object for the app to stream back to the client itself, rather
    than redirecting to a presigned MinIO URL — MinIO has no published host port (see
    docker-compose.yml) and is meant to stay fully internal, so a URL pointing directly
    at it (using the `minio` service hostname) would be unreachable by any real client.
    `range_header` is passed straight through from the client's own Range header so
    HTML5 video seeking works."""
    kwargs = {"Bucket": S3_BUCKET, "Key": object_key}
    if range_header:
        kwargs["Range"] = range_header
    return _client().get_object(**kwargs)


def delete_video(object_key: str) -> None:
    _client().delete_object(Bucket=S3_BUCKET, Key=object_key)


def copy_video(old_key: str, new_key: str) -> None:
    """Renames an object (MinIO/S3 has no atomic rename) — used one-off by the
    `migrate-video-keys` CLI command to move pre-per-user-scoping objects onto the new
    stories/<user_id>/<story_id>/video.mp4 layout."""
    client = _client()
    client.copy_object(Bucket=S3_BUCKET, CopySource={"Bucket": S3_BUCKET, "Key": old_key}, Key=new_key)
    client.delete_object(Bucket=S3_BUCKET, Key=old_key)
