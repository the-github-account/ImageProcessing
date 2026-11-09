import argparse
import logging
import os
import queue
import threading
import time
from pathlib import Path

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

from config import (
    DRIVE_CREDENTIALS_FILE, DRIVE_CLIENT_SECRETS_FILE, DRIVE_FOLDER_ID,
    UPLOAD_MAX_ATTEMPTS,
)

log = logging.getLogger(__name__)

class DriveUploader:
    """Single-worker uploader: serializes Drive API calls and retains failed local files."""

    def __init__(self, drive):
        self.drive = drive
        self._api_lock = threading.RLock()
        self._queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="drive-uploader", daemon=True)
        self._worker.start()

    def enqueue(self, path):
        path = Path(path)
        if path.exists():
            self._queue.put(path)
            log.info("Queued for Drive upload: %s", path.name)

    def _upload_one(self, path):
        metadata = {"title": path.name}
        if DRIVE_FOLDER_ID:
            metadata["parents"] = [{"id": DRIVE_FOLDER_ID}]
        with self._api_lock:
            remote = self.drive.CreateFile(metadata)
            remote.SetContentFile(str(path))
            remote.Upload()
        log.info("Uploaded to Google Drive: %s", path.name)
        try:
            path.unlink()
            log.info("Removed local copy after successful upload: %s", path.name)
        except OSError:
            log.exception("Upload succeeded but local cleanup failed: %s", path)

    def _run(self):
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                path = Path(item)
                if not path.exists():
                    continue
                for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):
                    try:
                        self._upload_one(path)
                        break
                    except Exception:
                        log.exception("Drive upload attempt %d/%d failed for %s",
                                      attempt, UPLOAD_MAX_ATTEMPTS, path.name)
                        if attempt < UPLOAD_MAX_ATTEMPTS:
                            time.sleep(min(2 ** attempt, 60))
                        else:
                            log.error("Keeping local file for manual retry: %s", path)
            finally:
                self._queue.task_done()

    def cleanup_old_files(self, retention_days):
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        query = "trashed=false"
        if DRIVE_FOLDER_ID:
            query = f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"
        deleted = 0

        # Hold the API lock only while listing. Do not hold it across the
        # entire deletion batch, otherwise uploads wait until every old file
        # has been deleted.
        with self._api_lock:
            remote_files = self.drive.ListFile({"q": query, "maxResults": 1000}).GetList()

        for item in remote_files:
            name = item.get("title", "").lower()
            if not name.endswith((".jpg", ".mp4")):
                continue

            modified = item.get("modifiedDate")
            if not modified:
                continue

            try:
                stamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            except ValueError:
                log.warning("Skipping file with unrecognized modifiedDate: %s", name)
                continue

            if stamp < cutoff:
                try:
                    # One delete per lock acquisition lets the upload worker
                    # use the Drive connection between cleanup operations.
                    with self._api_lock:
                        item.Delete()
                    deleted += 1
                    log.info("Deleted expired Drive file: %s", name)

                    # Briefly yield so queued uploads get a chance to run.
                    time.sleep(0.1)
                except Exception:
                    log.exception("Could not delete expired Drive file: %s", name)

        log.info("Drive retention cleanup complete; deleted %d files", deleted)

    def shutdown(self, wait=True):
        if wait:
            self._queue.join()
        self._queue.put(None)
        self._worker.join(timeout=10)

def initialize_drive(interactive=False):
    """Load existing OAuth credentials. Interactive browser login is opt-in only."""
    gauth = GoogleAuth()
    credentials_file = str(DRIVE_CREDENTIALS_FILE)
    if os.path.exists(credentials_file):
        gauth.LoadCredentialsFile(credentials_file)

    if gauth.credentials is None:
        if not interactive:
            raise RuntimeError(
                f"Google Drive credentials not found at {credentials_file}. "
                "Run `python drive_uploader.py --auth` once from a terminal."
            )
        if not DRIVE_CLIENT_SECRETS_FILE.exists():
            raise RuntimeError(
                f"OAuth client file missing: {DRIVE_CLIENT_SECRETS_FILE}. "
                "Create a new OAuth client secret in Google Cloud and place it there."
            )
        # PyDrive2 reads client_secrets.json from its working directory by default.
        if DRIVE_CLIENT_SECRETS_FILE.name != "client_secrets.json":
            raise RuntimeError("For interactive setup, name the OAuth file client_secrets.json.")
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        if not getattr(gauth.credentials, "refresh_token", None):
            if not interactive:
                raise RuntimeError("Saved Google credentials have no refresh token; run --auth again.")
            gauth.LocalWebserverAuth()
        else:
            gauth.Refresh()
    else:
        gauth.Authorize()

    gauth.SaveCredentialsFile(credentials_file)
    return DriveUploader(GoogleDrive(gauth))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="perform one-time interactive Google OAuth login")
    args = parser.parse_args()
    if not args.auth:
        parser.error("Use --auth for the one-time interactive login.")
    uploader = initialize_drive(interactive=True)
    uploader.shutdown()
    print("Google Drive authentication saved.")
