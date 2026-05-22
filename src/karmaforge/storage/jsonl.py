"""JSONL read/write helpers with gzip support."""

import gzip
import json
from pathlib import Path
from typing import Iterator


def write_jsonl(path: Path, records: list[dict], compress: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if compress else open
    mode = "wt" if compress else "w"
    with opener(str(path), mode, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterator[dict]:
    path = Path(path)
    if not path.exists():
        return
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt" if path.suffix == ".gz" else "r"
    with opener(str(path), mode, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def count_lines(path: Path) -> int:
    path = Path(path)
    if not path.exists():
        return 0
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt" if path.suffix == ".gz" else "r"
    count = 0
    with opener(str(path), mode, encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def load_all(path: Path) -> list[dict]:
    return list(read_jsonl(path))
