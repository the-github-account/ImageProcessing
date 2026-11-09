import cv2
from config import MIN_AREA, PERSISTENCE_FRAMES

class MotionDetector:
    def __init__(self):
        self.avg = None
        self.counter = 0

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.avg is None:
            self.avg = gray.astype("float")
            return False

        cv2.accumulateWeighted(gray, self.avg, 0.3)
        delta = cv2.absdiff(gray, cv2.convertScaleAbs(self.avg))
        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area = sum(cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 1000)

        self.counter = self.counter + 1 if area > MIN_AREA else 0
        return self.counter >= PERSISTENCE_FRAMES
