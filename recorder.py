import cv2
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from config import (
    TEMP_DIR, FPS, VIDEO_DURATION_LIMIT, SNAPSHOT_COUNT,
    SNAPSHOT_INTERVAL_SECONDS,
)

log = logging.getLogger(__name__)

class Recorder:
    def __init__(self, uploader):
        self.uploader = uploader
        self.recording = False
        self.writer = None
        self.started_at = 0.0
        self.last_snapshot_at = 0.0
        self.snapshot_count = 0
        self.video_path = None

    def start(self, frame):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.video_path = Path(TEMP_DIR) / f"{stamp}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(self.video_path), fourcc, FPS, frame.shape[1::-1])
        if not writer.isOpened():
            writer.release()
            self.video_path = None
            raise RuntimeError("OpenCV could not open the MP4 video writer.")
        self.writer = writer
        self.started_at = time.monotonic()
        self.last_snapshot_at = 0.0
        self.snapshot_count = 0
        self.recording = True
        log.info("Recording started: %s", self.video_path.name)

    def update(self, frame):
        if not self.recording or self.writer is None:
            return
        self.writer.write(frame)
        now = time.monotonic()
        if (self.snapshot_count < SNAPSHOT_COUNT and
                now - self.last_snapshot_at >= SNAPSHOT_INTERVAL_SECONDS):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            image_path = Path(TEMP_DIR) / f"{stamp}_{self.snapshot_count + 1}.jpg"
            if cv2.imwrite(str(image_path), frame):
                self.uploader.enqueue(image_path)
                self.snapshot_count += 1
                self.last_snapshot_at = now
            else:
                log.error("Could not write snapshot: %s", image_path)

    def should_stop(self):
        return self.recording and (time.monotonic() - self.started_at) >= VIDEO_DURATION_LIMIT

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        writer, self.writer = self.writer, None
        if writer is not None:
            writer.release()
        path, self.video_path = self.video_path, None
        if path and path.exists() and path.stat().st_size > 0:
            self.uploader.enqueue(path)
            log.info("Recording finalized and queued: %s", path.name)
        elif path:
            log.error("Recording file is empty or missing: %s", path)
