"""每次命令行会话一个 JSONL 文件，事件发生后立即落盘。"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

LOG_DIR = Path(__file__).resolve().parents[1] / 'logs'
LOCAL_TIME = timezone(timedelta(hours=8))
SENSITIVE_FIELDS = {'api_key', 'zzz_api_key', 'authorization', 'access_token', 'secret'}


class SessionLog:
    def __init__(self, directory=LOG_DIR):
        self.session_id = uuid4().hex
        self._key = os.environ.get('ZZZ_API_KEY', '').strip()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(LOCAL_TIME).strftime('%Y%m%d-%H%M%S')
        self.path = directory / f'{stamp}-{self.session_id[:8]}.jsonl'
        self.path.touch(mode=0o600, exist_ok=False)

    def _redact(self, value):
        if isinstance(value, dict):
            return {k: '[REDACTED]' if str(k).lower() in SENSITIVE_FIELDS else self._redact(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        if isinstance(value, str) and self._key:
            return value.replace(self._key, '[REDACTED]')
        return value

    def write(self, event, **fields):
        record = {'timestamp': datetime.now(LOCAL_TIME).isoformat(),
                  'session_id': self.session_id, 'event': event, **fields}
        line = json.dumps(self._redact(record), ensure_ascii=False,
                          default=lambda value: f'<{type(value).__name__}>')
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
