import re

LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
POSE_LINE_RE = re.compile(r"\bpose\b", re.IGNORECASE)


class PoseDetector:
    def detect_pose(self, lines):
        if not lines or not any(LETTER_RE.search(line) for line in lines):
            return False, "", "unreadable"
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if saw_prestations and POSE_LINE_RE.search(line):
                return True, "", "auto"
        return False, "", "auto"
