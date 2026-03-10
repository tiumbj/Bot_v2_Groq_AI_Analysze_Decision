"""
OracleBot-Pro
File: core/logger_engine.py
Version: v1.0.0

Purpose
- Append structured runtime logs for features, candidates, and guards
- JSONL format for easy downstream parsing
- Minimal, safe, production-lean logger

Output files
- storage/logs/feature_snapshots.jsonl
- storage/logs/candidate_events.jsonl
- storage/logs/guard_events.jsonl
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict


class LoggerEngine:
    def __init__(self, base_dir: str = "storage/logs") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.feature_log = self.base_dir / "feature_snapshots.jsonl"
        self.candidate_log = self.base_dir / "candidate_events.jsonl"
        self.guard_log = self.base_dir / "guard_events.jsonl"

    def log_feature_snapshot(self, snapshot: Any) -> None:
        payload = {
            "logged_at": datetime.utcnow().isoformat(),
            "type": "feature_snapshot",
            "payload": self._serialize(snapshot),
        }
        self._append_jsonl(self.feature_log, payload)

    def log_candidate_event(self, candidate: Any) -> None:
        payload = {
            "logged_at": datetime.utcnow().isoformat(),
            "type": "candidate_event",
            "payload": self._serialize(candidate),
        }
        self._append_jsonl(self.candidate_log, payload)

    def log_guard_decision(self, decision: Any) -> None:
        payload = {
            "logged_at": datetime.utcnow().isoformat(),
            "type": "guard_decision",
            "payload": self._serialize(decision),
        }
        self._append_jsonl(self.guard_log, payload)

    def _append_jsonl(self, file_path: Path, payload: Dict[str, Any]) -> None:
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=self._fallback_serializer))
            handle.write("\n")

    def _serialize(self, obj: Any) -> Any:
        if obj is None:
            return None

        if hasattr(obj, "to_dict"):
            try:
                return obj.to_dict()
            except Exception:
                pass

        if is_dataclass(obj):
            return asdict(obj)

        if isinstance(obj, dict):
            return {str(k): self._serialize(v) for k, v in obj.items()}

        if isinstance(obj, (list, tuple, set)):
            return [self._serialize(v) for v in obj]

        if isinstance(obj, Enum):
            return obj.value

        if isinstance(obj, datetime):
            return obj.isoformat()

        if hasattr(obj, "__dict__"):
            return {
                key: self._serialize(value)
                for key, value in vars(obj).items()
                if not key.startswith("_")
            }

        return obj

    @staticmethod
    def _fallback_serializer(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        return str(obj)