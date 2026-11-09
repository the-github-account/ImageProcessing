import os
# TCP is generally more resilient than UDP on lossy Wi-Fi links.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

import cv2
import logging
import threading
import time
from config import (
    RTSP_URL, FRAME_SIZE, CAMERA_RETRY_INITIAL_SECONDS,
    CAMERA_RETRY_MAX_SECONDS, CAMERA_READ_FAILURE_LIMIT, CAMERA_STALE_SECONDS,
)

log = logging.getLogger(__name__)

class Camera:
    """Owns the RTSP capture in one worker thread and publishes fresh frames."""

    def __init__(self):
        if not RTSP_URL or ":@" in RTSP_URL:
            raise RuntimeError(
                "Camera credentials are missing. Set TAPO_CAMERA_PASSWORD "
                "(and TAPO_CAMERA_USERNAME/TAPO_CAMERA_IP) in .env."
            )
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame = None
        self._frame_id = 0
        self._consumed_id = 0
        self._last_frame_at = 0.0
        self._thread = threading.Thread(target=self._capture_loop, name="rtsp-capture", daemon=True)
        self._thread.start()

    def _open(self):
        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _capture_loop(self):
        delay = CAMERA_RETRY_INITIAL_SECONDS
        failures = 0
        cap = None
        try:
            while not self._stop.is_set():
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    log.warning("Opening camera RTSP stream")
                    cap = self._open()
                    if not cap.isOpened():
                        log.error("Unable to open RTSP stream; retrying in %.1fs", delay)
                        cap.release()
                        cap = None
                        self._stop.wait(delay)
                        delay = min(delay * 2, CAMERA_RETRY_MAX_SECONDS)
                        continue
                    delay = CAMERA_RETRY_INITIAL_SECONDS
                    failures = 0
                    log.info("Camera stream connected")

                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= CAMERA_READ_FAILURE_LIMIT:
                        log.warning("RTSP read failed %d times; reconnecting", failures)
                        cap.release()
                        cap = None
                        self._stop.wait(1)
                        failures = 0
                    else:
                        self._stop.wait(0.1)
                    continue

                failures = 0
                frame = cv2.resize(frame, FRAME_SIZE)
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
                    self._last_frame_at = time.monotonic()
        finally:
            if cap is not None:
                cap.release()

    def get_frame(self):
        """Return a new frame once; None means no new frame is available."""
        with self._lock:
            if self._frame is None or self._frame_id == self._consumed_id:
                return None
            self._consumed_id = self._frame_id
            return self._frame.copy()

    def is_stale(self):
        with self._lock:
            return self._last_frame_at == 0 or (
                time.monotonic() - self._last_frame_at > CAMERA_STALE_SECONDS
            )

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=6)
