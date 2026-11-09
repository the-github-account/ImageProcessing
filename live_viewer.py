#!/usr/bin/env python3
"""Desktop viewer for the Tapo daemon's localhost MJPEG preview stream."""
import time
import cv2

STREAM_URL = "http://127.0.0.1:8765/stream"
WINDOW_NAME = "Tapo Live Camera"


def main():
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 960, 540)
    capture = None
    try:
        while True:
            if capture is None or not capture.isOpened():
                if capture is not None:
                    capture.release()
                capture = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
                if not capture.isOpened():
                    print("Waiting for Tapo daemon live stream...")
                    capture.release()
                    capture = None
                    if cv2.waitKey(500) & 0xFF == ord('q'):
                        break
                    continue
            ok, frame = capture.read()
            if ok and frame is not None:
                cv2.imshow(WINDOW_NAME, frame)
            else:
                capture.release()
                capture = None
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            try:
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
