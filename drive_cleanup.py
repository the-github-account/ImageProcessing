import logging
import threading
from config import DRIVE_RETENTION_DAYS, DRIVE_CLEANUP_INTERVAL_HOURS

log = logging.getLogger(__name__)

def cleanup_loop(uploader, stop_event):
    log.info("Google Drive retention cleanup worker started")
    interval = max(1, DRIVE_CLEANUP_INTERVAL_HOURS) * 3600
    while not stop_event.is_set():
        try:
            uploader.cleanup_old_files(DRIVE_RETENTION_DAYS)
        except Exception:
            log.exception("Google Drive cleanup failed; will retry next cycle")
        stop_event.wait(interval)
