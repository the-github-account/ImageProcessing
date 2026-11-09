import cv2
import logging
from ultralytics import YOLO
from config import YOLO_MODEL, YOLO_CONF, MIN_PERSON_AREA

log = logging.getLogger(__name__)
_model = None

def load_model():
    global _model
    if _model is None:
        log.info("Loading human detection model: %s", YOLO_MODEL)
        _model = YOLO(YOLO_MODEL)
    return _model

def human_present(frame):
    model = load_model()
    small = cv2.resize(frame, (640, 360))
    results = model(small, conf=YOLO_CONF, classes=[0], verbose=False)
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        if (x2 - x1) * (y2 - y1) >= MIN_PERSON_AREA:
            return True
    return False
