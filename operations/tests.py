from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import TestCase

from operations.services.backups import _delete_older_than


class _FakeClient:
    def __init__(self):
        self.deleted = []

    def delete_object(self, *, Bucket, Key):
        self.deleted.append((Bucket, Key))


class _FakeSpaces:
    def __init__(self, bucket="test-bucket"):
        self.bucket = bucket
        self.client = _FakeClient()


class BackupRetentionTests(TestCase):
    def test_delete_old_backups_in_folder_and_legacy_flat_layout(self):
        now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
        old = now - timedelta(days=31)
        recent = now - timedelta(days=3)
        objs = [
            {"Key": "backups/operations/2026/01/operations-1.db.gz", "LastModified": old},
            {"Key": "backups/operations-20260101.db.gz", "LastModified": old},
            {"Key": "backups/operations2-20260101.db.gz", "LastModified": old},
            {"Key": "backups/operations/2026/04/operations-2.db.gz", "LastModified": recent},
        ]
        spaces = _FakeSpaces()

        with patch("operations.services.backups._utc_now", return_value=now):
            with patch("operations.services.backups._list_objects", return_value=objs):
                deleted, kept = _delete_older_than(
                    spaces,
                    prefix="backups/operations/",
                    max_days=30,
                    dry_run=False,
                )

        self.assertEqual(deleted, 2)
        self.assertEqual(kept, 1)
        self.assertEqual(
            [k for _, k in spaces.client.deleted],
            [
                "backups/operations/2026/01/operations-1.db.gz",
                "backups/operations-20260101.db.gz",
            ],
        )
