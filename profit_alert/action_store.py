"""Trava persistente: no máximo uma tentativa de zeramento por dia local."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path


class ActionStore:
    def __init__(self, path: Path | None = None) -> None:
        appdata = os.environ.get("LOCALAPPDATA")
        if path is None and not appdata:
            raise RuntimeError("LOCALAPPDATA indisponível; automação desativada.")
        self.path = path or Path(appdata) / "LeitorProfit" / "action-state.json"

    def reserve(self, day: date, pid: int) -> bool:
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("date"), str):
                raise ValueError("Estado anterior da ação inválido; automação desativada.")
            if state.get("date") == day.isoformat():
                return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"date": day.isoformat(), "pid": pid, "status": "attempted",
                "at": datetime.now().isoformat(timespec="seconds")}
        fd, name = tempfile.mkstemp(prefix="action-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return True
