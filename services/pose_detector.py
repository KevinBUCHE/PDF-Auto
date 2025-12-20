import re

POSE_RE = re.compile(r"Pose\s+au[^0-9]*([0-9][0-9\s\u202f]*[\.,][0-9]{2})", re.IGNORECASE)


class PoseDetector:
    def detect_pose(self, lines):
        for line in lines:
            match = POSE_RE.search(line)
            if match:
                amount = match.group(1)
                amount = amount.replace("\u202f", " ").replace(" ", "")
                if "." in amount:
                    amount = amount.replace(".", ",")
                return True, amount
        return False, ""
