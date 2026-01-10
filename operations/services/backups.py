from __future__ import annotations

import gzip
import io
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from operations.models import BackupRun
from services.spaces import SpacesClient  # update to your actual import path


@dataclass
class BackupResult:
    ok: bool
    db_path: str
    key: str
    bucket: str
    region: str
    endpoint: str
    uploaded_bytes: int
    compressed: bool
    max_days: int
    deleted_old: int
    kept: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_key(prefix: str, filename: str, now: Optional[datetime] = None) -> str:
    now = now or _utc_now()
    y = now.strftime("%Y")
    m = now.strftime("%m")
    ts = now.strftime("%Y%m%d-%H%M%S")
    prefix = prefix.strip("/")
    return f"{prefix}/{y}/{m}/{filename}-{ts}.db"


def _read_db_bytes(db_path: str) -> bytes:
    with open(db_path, "rb") as f:
        return f.read()


def _gzip_bytes(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        gz.write(raw)
    return buf.getvalue()


def _list_objects(client, bucket: str, prefix: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        out.extend(resp.get("Contents", []) or [])
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return out


def _delete_older_than(
    spaces: SpacesClient,
    prefix: str,
    max_days: int,
    dry_run: bool,
) -> Tuple[int, int]:
    cutoff = _utc_now() - timedelta(days=max_days)
    objs = _list_objects(spaces.client, spaces.bucket, prefix)

    deleted = 0
    kept = 0
    for obj in objs:
        key = obj["Key"]
        last_modified = obj.get("LastModified")  # tz-aware datetime
        if last_modified is None:
            kept += 1
            continue

        if last_modified < cutoff:
            if not dry_run:
                spaces.client.delete_object(Bucket=spaces.bucket, Key=key)
            deleted += 1
        else:
            kept += 1

    return deleted, kept


def backup_sqlite_db_to_spaces(
    *,
    db_path: str = "/data/operations.db",
    target: str = "operations_db",
    prefix: str = "backups/operations",
    filename: str = "operations",
    max_days: int = 30,
    gzip_enabled: bool = True,
    acl: str = "private",
    dry_run: bool = False,
    # New:
    backup_run: Optional[BackupRun] = None,
) -> BackupResult:
    """
    Back up SQLite DB to Spaces + apply retention. Optionally writes to BackupRun.
    """
    if max_days < 1:
        raise ValueError("max_days must be >= 1")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found at {db_path}")

    spaces = SpacesClient()
    now = _utc_now()

    key = _default_key(prefix=prefix, filename=filename, now=now)
    content_type = "application/octet-stream"

    raw = _read_db_bytes(db_path)
    data = raw
    compressed = False

    if gzip_enabled:
        data = _gzip_bytes(raw)
        compressed = True
        key = key + ".gz"
        content_type = "application/gzip"

    uploaded_bytes = len(data)

    # Upload
    if not dry_run:
        spaces.client.put_object(
            Bucket=spaces.bucket,
            Key=key,
            Body=data,
            ACL=acl,
            ContentType=content_type,
        )

    # Retention cleanup
    deleted_old, kept = _delete_older_than(
        spaces,
        prefix=prefix.strip("/") + "/",
        max_days=max_days,
        dry_run=dry_run,
    )

    result = BackupResult(
        ok=True,
        db_path=db_path,
        key=key,
        bucket=spaces.bucket,
        region=spaces.region,
        endpoint=spaces.endpoint,
        uploaded_bytes=uploaded_bytes,
        compressed=compressed,
        max_days=max_days,
        deleted_old=deleted_old,
        kept=kept,
    )

    # Persist to history if provided
    if backup_run is not None:
        backup_run.mark_success(
            bucket=result.bucket,
            region=result.region,
            endpoint=result.endpoint,
            key=result.key,
            uploaded_bytes=result.uploaded_bytes,
            compressed=result.compressed,
            deleted_old=result.deleted_old,
            kept=result.kept,
        )

    return result
