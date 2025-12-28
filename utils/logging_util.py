from datetime import datetime
from pathlib import Path


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = message.splitlines() or [""]
    with log_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"[{timestamp}] {line}\n")
