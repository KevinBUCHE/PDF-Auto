import re

POSE_LABEL_RE = re.compile(r"pose\s+au", re.IGNORECASE)
AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


class PoseDetector:
    def detect_pose(self, lines):
        if not lines or not any(LETTER_RE.search(line) for line in lines):
            return False, "", "unreadable"
        for index, line in enumerate(lines):
            if not POSE_LABEL_RE.search(line):
                continue
            amount = self._extract_amount(line)
            if not amount and index + 1 < len(lines):
                amount = self._extract_amount(lines[index + 1])
            if not amount and index - 1 >= 0:
                amount = self._extract_amount(lines[index - 1])
            if amount:
                return True, amount, "auto"
        return False, "", "auto"

    def _extract_amount(self, text):
        match = AMOUNT_RE.search(text)
        if not match:
            return ""
        amount = match.group(1)
        amount = amount.replace("\u202f", " ")
        amount = re.sub(r"[€\s]", "", amount)
        if "," in amount and "." in amount:
            amount = amount.replace(".", "")
        if "." in amount:
            amount = amount.replace(".", ",")
        return amount
