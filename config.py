import os
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent

def _env(name, default):
    value = os.getenv(name)
    return value if value not in (None, "") else default

# Camera: defaults preserve the modular config you supplied.
CAMERA_IP = _env("TAPO_CAMERA_IP", "192.168.1.22")
CAMERA_USERNAME = _env("TAPO_CAMERA_USERNAME", "tapoadmin")
CAMERA_PASSWORD = _env("TAPO_CAMERA_PASSWORD", "")
RTSP_URL = _env(
    "TAPO_RTSP_URL",
    f"rtsp://{quote(CAMERA_USERNAME, safe='')}:{quote(CAMERA_PASSWORD, safe='')}@{CAMERA_IP}:554/stream1",
)
FRAME_SIZE = (640, 360)
CAMERA_RETRY_INITIAL_SECONDS = 1
CAMERA_RETRY_MAX_SECONDS = 30
CAMERA_READ_FAILURE_LIMIT = 5
CAMERA_STALE_SECONDS = 10

# Motion detection
MIN_AREA = int(_env("TAPO_MIN_AREA", "5000"))
PERSISTENCE_FRAMES = int(_env("TAPO_PERSISTENCE_FRAMES", "2"))
COOLDOWN_SECONDS = float(_env("TAPO_COOLDOWN_SECONDS", "5"))

# Video and snapshots
FPS = float(_env("TAPO_RECORDING_FPS", "20"))
VIDEO_DURATION_LIMIT = int(_env("TAPO_VIDEO_DURATION_LIMIT", "30"))
SNAPSHOT_COUNT = int(_env("TAPO_SNAPSHOT_COUNT", "3"))
SNAPSHOT_INTERVAL_SECONDS = float(_env("TAPO_SNAPSHOT_INTERVAL_SECONDS", "0.5"))

# Human detection
YOLO_MODEL = _env("TAPO_YOLO_MODEL", "yolov8n.pt")
YOLO_CONF = float(_env("TAPO_YOLO_CONF", "0.4"))
MIN_PERSON_AREA = int(_env("TAPO_MIN_PERSON_AREA", "8000"))

# Google Drive
DRIVE_FOLDER_ID = _env("GOOGLE_DRIVE_FOLDER_ID", "1CPOTWoHISUmdea0z0t2rQp0YEcXSpN78")
DRIVE_RETENTION_DAYS = int(_env("DRIVE_RETENTION_DAYS", "15"))
DRIVE_CLEANUP_INTERVAL_HOURS = int(_env("DRIVE_CLEANUP_INTERVAL_HOURS", "24"))
DRIVE_CREDENTIALS_FILE = Path(_env("GOOGLE_DRIVE_CREDENTIALS_FILE", str(BASE_DIR / "mycreds.txt")))
DRIVE_CLIENT_SECRETS_FILE = Path(_env("GOOGLE_CLIENT_SECRETS_FILE", str(BASE_DIR / "client_secrets.json")))
UPLOAD_MAX_ATTEMPTS = int(_env("UPLOAD_MAX_ATTEMPTS", "5"))

# Temporary media: files are removed only after successful Drive upload.
TEMP_DIR = Path(_env("TAPO_TEMP_DIR", str(Path.home() / "tapo_tmp")))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = _env("TAPO_LOG_LEVEL", "INFO").upper()
