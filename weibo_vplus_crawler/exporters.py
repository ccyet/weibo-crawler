from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List


@dataclass
class OutputPaths:
    root_dir: str
    posts_jsonl: str
    posts_csv: str
    articles_jsonl: str
    articles_csv: str
    skipped_unknown_jsonl: str
    errors_jsonl: str
    manifest_json: str


def build_output_paths(base_out_dir: str, uid: str, started_at: datetime) -> OutputPaths:
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    root_dir = os.path.abspath(os.path.join(base_out_dir, uid, timestamp))
    os.makedirs(root_dir, exist_ok=True)
    return OutputPaths(
        root_dir=root_dir,
        posts_jsonl=os.path.join(root_dir, "posts.jsonl"),
        posts_csv=os.path.join(root_dir, "posts.csv"),
        articles_jsonl=os.path.join(root_dir, "articles.jsonl"),
        articles_csv=os.path.join(root_dir, "articles.csv"),
        skipped_unknown_jsonl=os.path.join(root_dir, "skipped_unknown.jsonl"),
        errors_jsonl=os.path.join(root_dir, "errors.jsonl"),
        manifest_json=os.path.join(root_dir, "manifest.json"),
    )


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        if not rows:
            return

        normalized = [flatten_for_csv(row) for row in rows]
        fieldnames = sorted({key for row in normalized for key in row.keys()})
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)


def write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def flatten_for_csv(item: Dict[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, ensure_ascii=False)
        else:
            flattened[key] = value
    return flattened
