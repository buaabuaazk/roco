"""按北京时间汇总页面访问；匿名浏览器标识按天哈希去重。"""
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo


class Visits:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE IF NOT EXISTS visits (day TEXT PRIMARY KEY, pv INTEGER NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS visitors '
                               '(day TEXT NOT NULL, browser TEXT NOT NULL, PRIMARY KEY (day, browser))')

    @staticmethod
    def today():
        return datetime.now(ZoneInfo('Asia/Shanghai')).date()

    def record(self, visitor_id=None):
        day = self.today().isoformat()
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute('INSERT INTO visits(day, pv) VALUES (?, 1) '
                               'ON CONFLICT(day) DO UPDATE SET pv=pv+1', (day,))
            if visitor_id:
                digest = hashlib.sha256(f'{day}:{visitor_id}'.encode()).hexdigest()
                connection.execute('INSERT OR IGNORE INTO visitors(day, browser) VALUES (?, ?)', (day, digest))

    def snapshot(self):
        today = self.today()
        days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            total = connection.execute('SELECT COALESCE(SUM(pv),0) FROM visits').fetchone()[0]
            pv = dict(connection.execute('SELECT day, pv FROM visits WHERE day>=?', (days[0],)))
            uv = dict(connection.execute('SELECT day, COUNT(*) FROM visitors WHERE day>=? GROUP BY day', (days[0],)))
        return {'timezone': 'Asia/Shanghai', 'total_pv': total,
                'today_pv': pv.get(days[-1], 0), 'today_uv': uv.get(days[-1], 0),
                'days': [{'day': day, 'pv': pv.get(day, 0), 'uv': uv.get(day, 0)} for day in days]}
