# Top Version 1.1 - 2026-11-09
# Load the project-local .env before importing config or other modules
# that read environment variables.
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import signal
import threading
import time

import cv2

from config import COOLDOWN_SECONDS, LOG_LEVEL, FPS
from camera import Camera
from motion import MotionDetector
from human_detector import load_model, human_present
from recorder import Recorder
from drive_uploader import initialize_drive
from drive_cleanup import cleanup_loop

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("tapo")

# While recording, re-check for a person periodically even if there is no
# fresh motion event. This lets a stationary person keep the recording alive.
HUMAN_RECHECK_SECONDS = 0.5

# Set to 1 to enable Google Drive retention deletion; set to 0 to disable it.
# Camera monitoring, recording and uploads continue either way.
ENABLE_DRIVE_DELETION = 0

# Keep the live preview running alongside detection/recording. The window's
# normal minimize button hides it without stopping camera processing.
ENABLE_LIVE_DISPLAY = 1
LIVE_WINDOW_NAME = "Tapo Live Camera"



class _LivePreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address):
        self.frame_condition = threading.Condition()
        self.latest_frame = None
        self.frame_number = 0
        super().__init__(address, _LivePreviewHandler)

    def publish(self, frame):
        with self.frame_condition:
            self.latest_frame = frame.copy()
            self.frame_number += 1
            self.frame_condition.notify_all()


class _LivePreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/stream"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        last_number = -1
        try:
            while True:
                with self.server.frame_condition:
                    self.server.frame_condition.wait_for(
                        lambda: self.server.frame_number != last_number,
                        timeout=5.0,
                    )
                    if self.server.frame_number == last_number:
                        continue
                    frame = self.server.latest_frame
                    last_number = self.server.frame_number
                if frame is None:
                    continue
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue
                payload = encoded.tobytes()
                self.wfile.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                    + payload + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, _format, *_args):
        # Keep routine browser reconnects out of the CCTV log.
        return


def start_live_preview_server():
    server = _LivePreviewHTTPServer(("127.0.0.1", 8765))
    thread = threading.Thread(
        target=server.serve_forever, name="live-preview-http", daemon=True
    )
    thread.start()
    log.info("Live preview stream available on http://127.0.0.1:8765/stream")
    return server

def main():
    stop_event = threading.Event()
    camera = None
    recorder = None
    uploader = None
    cleanup_thread = None
    live_display = False
    preview_server = None

    def request_stop(signum, _frame):
        log.info("Received signal %s; shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        # Keep the existing startup, camera, model, Drive and cleanup setup.
        uploader = initialize_drive(interactive=False)
        load_model()
        camera = Camera()
        motion = MotionDetector()

        if ENABLE_LIVE_DISPLAY:
            try:
                preview_server = start_live_preview_server()
            except OSError:
                log.exception("Unable to start the live preview stream; monitoring will continue")
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                try:
                    cv2.namedWindow(LIVE_WINDOW_NAME, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(LIVE_WINDOW_NAME, 960, 540)
                    live_display = True
                    log.info(
                        "Live camera display enabled; minimize its window to hide "
                        "the preview without stopping monitoring"
                    )
                except cv2.error:
                    log.exception("Unable to open live camera display; continuing without preview")
            else:
                log.warning(
                    "No desktop display detected; live preview is unavailable in this session"
                )
        recorder = Recorder(uploader)

        if ENABLE_DRIVE_DELETION == 1:
            cleanup_thread = threading.Thread(
                target=cleanup_loop, args=(uploader, stop_event),
                name="drive-retention", daemon=True,
            )
            cleanup_thread.start()
            log.info("Google Drive retention deletion is ENABLED")
        else:
            log.info("Google Drive retention deletion is DISABLED")

        log.info("Human-only Tapo detection started")
        last_human_seen = 0.0
        next_human_check = 0.0
        frame_interval = 1.0 / FPS if FPS > 0 else 0.05
        next_frame_time = time.monotonic()

        while not stop_event.is_set():
            frame = camera.get_frame()
            if frame is None:
                if live_display:
                    cv2.waitKey(1)
                if camera.is_stale():
                    log.warning("Camera frame is stale; waiting for RTSP reconnection")
                stop_event.wait(0.05)
                next_frame_time = time.monotonic()
                continue

            now = time.monotonic()
            if preview_server is not None:
                preview_server.publish(frame)
            motion_detected = motion.detect(frame)

            # Check immediately on motion; while recording, also re-check
            # every 0.5 seconds so a stationary person is still detected.
            check_for_human = motion_detected or (
                recorder.recording and now >= next_human_check
            )
            human_detected = False

            if check_for_human:
                human_detected = human_present(frame)
                next_human_check = now + HUMAN_RECHECK_SECONDS

            if human_detected:
                last_human_seen = now
                if not recorder.recording:
                    recorder.start(frame)

            # KEY RECORDING FIX: write every captured frame while recording,
            # not only frames where motion and YOLO both return True.
            if recorder.recording:
                recorder.update(frame)

                if recorder.should_stop():
                    log.info("Maximum video duration reached")
                    recorder.stop()
                elif now - last_human_seen >= COOLDOWN_SECONDS:
                    log.info("No human detected during cooldown; stopping recording")
                    recorder.stop()

            # Show every fresh camera frame. Minimizing the native window does
            # not stop this loop, detection, recording, or uploads.
            if live_display:
                try:
                    cv2.imshow(LIVE_WINDOW_NAME, frame)
                    cv2.waitKey(1)
                except cv2.error:
                    log.exception("Live preview failed; camera monitoring will continue")
                    live_display = False
                    try:
                        cv2.destroyWindow(LIVE_WINDOW_NAME)
                    except cv2.error:
                        pass

            # Match the configured recording FPS instead of writing frames
            # as fast as the Python loop can run.
            next_frame_time += frame_interval
            delay = next_frame_time - time.monotonic()
            if delay > 0:
                stop_event.wait(delay)
            else:
                next_frame_time = time.monotonic()

    except Exception:
        log.exception("CCTV application stopped because of an unrecoverable error")
        raise
    finally:
        stop_event.set()
        if recorder is not None:
            recorder.stop()
        if camera is not None:
            camera.stop()
        if live_display:
            cv2.destroyAllWindows()
        if preview_server is not None:
            preview_server.shutdown()
            preview_server.server_close()
        if cleanup_thread is not None:
            cleanup_thread.join(timeout=2)
        if uploader is not None:
            uploader.shutdown(wait=True)
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
