"""Database access for the VisionIQ backend.

MySQL (the original setup, e.g. Aiven) is used when backend/.env has MySQL credentials; otherwise --
or when MySQL can't be reached at startup -- a local SQLite file is used instead, so the API always
starts with a working database (the Node version fell back to an in-memory users list only).

All SQL in this backend is written with %s placeholders; they are converted to ? for SQLite.
"""
import os
import queue
import sqlite3
import ssl
import threading
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import bcrypt

BACKEND_DIR = Path(__file__).resolve().parent.parent

_PLACEHOLDER_VALUES = {'', 'your_mysql_user', 'your_mysql_password'}


def hash_password(password, rounds=12):
    # bcryptjs silently uses only the first 72 bytes; python bcrypt>=5 raises instead, so truncate the same way
    return bcrypt.hashpw(str(password).encode('utf-8')[:72], bcrypt.gensalt(rounds)).decode('utf-8')


def check_password(password, hashed):
    try:
        return bcrypt.checkpw(str(password).encode('utf-8')[:72], str(hashed).encode('utf-8'))
    except ValueError:
        return False


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


class Database:
    def __init__(self):
        self.engine = None
        self._mysql_pool = None
        self._mysql_kwargs = None
        self._sqlite = None
        self._sqlite_lock = threading.RLock()

    # ---------------- connection setup ----------------
    def _mysql_configured(self):
        choice = os.getenv('DB_ENGINE', 'auto').strip().lower()
        if choice == 'sqlite':
            return False
        if choice == 'mysql':
            return True
        return (os.getenv('MYSQL_USER', '').strip() not in _PLACEHOLDER_VALUES
                and os.getenv('MYSQL_PASSWORD', '').strip() not in _PLACEHOLDER_VALUES)

    def _connect_mysql(self):
        import pymysql
        from pymysql.cursors import DictCursor

        ssl_enabled = os.getenv('MYSQL_SSL', 'true').strip().lower() != 'false'
        ssl_ctx = None
        if ssl_enabled:  # same as Node's ssl: { rejectUnauthorized: false }
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        self._mysql_kwargs = dict(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'vision_iq'),
            ssl=ssl_ctx,
            connect_timeout=5,
            autocommit=True,
            charset='utf8mb4',
            cursorclass=DictCursor,
        )
        conn = pymysql.connect(**self._mysql_kwargs)  # probe: raises if unreachable / bad credentials
        conn.ping()
        self._mysql_pool = queue.LifoQueue(maxsize=10)
        self._mysql_pool.put(conn)
        self.engine = 'mysql'

    def _connect_sqlite(self):
        path = Path(os.getenv('SQLITE_PATH', str(BACKEND_DIR / 'data' / 'visioniq.db')))
        path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._sqlite.row_factory = sqlite3.Row
        self._sqlite.execute('PRAGMA journal_mode=WAL')
        self.sqlite_path = path
        self.engine = 'sqlite'

    def connect(self):
        """Returns (engine, error). Tries MySQL when configured, falls back to SQLite."""
        error = None
        if self._mysql_configured():
            try:
                self._connect_mysql()
                return self.engine, None
            except Exception as exc:  # noqa: BLE001 -- any failure means: use SQLite
                error = exc
        self._connect_sqlite()
        return self.engine, error

    # ---------------- query helpers ----------------
    @contextmanager
    def _cursor(self):
        if self.engine == 'mysql':
            import pymysql
            try:
                conn = self._mysql_pool.get_nowait()
            except queue.Empty:
                conn = pymysql.connect(**self._mysql_kwargs)
            try:
                conn.ping(reconnect=True)
                with conn.cursor() as cur:
                    yield cur
            finally:
                try:
                    self._mysql_pool.put_nowait(conn)
                except queue.Full:
                    conn.close()
        else:
            with self._sqlite_lock:
                cur = self._sqlite.cursor()
                try:
                    yield cur
                finally:
                    cur.close()

    def _sql(self, sql):
        return sql.replace('%s', '?') if self.engine == 'sqlite' else sql

    def query(self, sql, params=()):
        """SELECT -> list of plain dicts (Decimal converted to float)."""
        with self._cursor() as cur:
            cur.execute(self._sql(sql), tuple(params))
            rows = cur.fetchall()
        return [{k: _plain(row[k]) for k in row.keys()} for row in rows]

    def execute(self, sql, params=()):
        with self._cursor() as cur:
            cur.execute(self._sql(sql), tuple(params))
            return cur.rowcount

    def executemany(self, sql, seq):
        seq = [tuple(p) for p in seq]
        if not seq:
            return 0
        with self._cursor() as cur:
            if self.engine == 'sqlite':
                cur.execute('BEGIN')
                try:
                    cur.executemany(self._sql(sql), seq)
                    cur.execute('COMMIT')
                except Exception:
                    cur.execute('ROLLBACK')
                    raise
            else:
                cur.executemany(sql, seq)
            return cur.rowcount

    # dialect-specific statement fragments
    def insert_ignore(self):
        return 'INSERT IGNORE' if self.engine == 'mysql' else 'INSERT OR IGNORE'

    def upsert_suffix(self, conflict_cols, update_cols):
        if self.engine == 'mysql':
            return ' ON DUPLICATE KEY UPDATE ' + ', '.join(f'{c} = VALUES({c})' for c in update_cols)
        return (f" ON CONFLICT({', '.join(conflict_cols)}) DO UPDATE SET "
                + ', '.join(f'{c} = excluded.{c}' for c in update_cols))

    def column_names(self, table):
        if self.engine == 'mysql':
            rows = self.query('SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS '
                              'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s', (table,))
        else:
            rows = self.query(f'PRAGMA table_info({table})')
        return {r['name'] for r in rows}


db = Database()
_status = {'connected': False, 'mock': False, 'engine': None}

MYSQL_TABLES = [
    """CREATE TABLE IF NOT EXISTS users (
        id INT UNSIGNED NOT NULL AUTO_INCREMENT,
        username VARCHAR(100) NOT NULL UNIQUE,
        email VARCHAR(255) NOT NULL UNIQUE,
        password VARCHAR(255) NOT NULL,
        role VARCHAR(30) NOT NULL DEFAULT 'admin',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS vehicle_events (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        csv_record_id VARCHAR(120) NOT NULL,
        timestamp_ist VARCHAR(80) NULL,
        vehicle_type VARCHAR(80) NULL,
        vehicle_number_plate VARCHAR(80) NULL,
        plate_confidence DECIMAL(6,4) NULL,
        vehicle_image TEXT NULL,
        speed DECIMAL(10,2) NULL,
        speed_limit DECIMAL(10,2) NULL,
        over_speed VARCHAR(20) NULL,
        latitude DECIMAL(12,7) NULL,
        longitude DECIMAL(12,7) NULL,
        video_clip_path TEXT NULL,
        vehicle_image_path TEXT NULL,
        plate_image_path TEXT NULL,
        events VARCHAR(255) NULL,
        source_file VARCHAR(255) NOT NULL,
        location VARCHAR(255) NULL,
        camera VARCHAR(120) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY vehicle_event_source_record (source_file, csv_record_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS nh5_imports (
        job_id VARCHAR(40) NOT NULL,
        source_file VARCHAR(255) NOT NULL,
        meta_mtime DOUBLE NOT NULL,
        record_count INT NOT NULL DEFAULT 0,
        imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (job_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS app_settings (
        name VARCHAR(64) NOT NULL,
        value TEXT NULL,
        PRIMARY KEY (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

SQLITE_TABLES = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS vehicle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        csv_record_id TEXT NOT NULL,
        timestamp_ist TEXT NULL,
        vehicle_type TEXT NULL,
        vehicle_number_plate TEXT NULL,
        plate_confidence REAL NULL,
        vehicle_image TEXT NULL,
        speed REAL NULL,
        speed_limit REAL NULL,
        over_speed TEXT NULL,
        latitude REAL NULL,
        longitude REAL NULL,
        video_clip_path TEXT NULL,
        vehicle_image_path TEXT NULL,
        plate_image_path TEXT NULL,
        events TEXT NULL,
        source_file TEXT NOT NULL,
        location TEXT NULL,
        camera TEXT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (source_file, csv_record_id)
    )""",
    """CREATE TABLE IF NOT EXISTS nh5_imports (
        job_id TEXT PRIMARY KEY,
        source_file TEXT NOT NULL,
        meta_mtime REAL NOT NULL,
        record_count INTEGER NOT NULL DEFAULT 0,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS app_settings (
        name TEXT PRIMARY KEY,
        value TEXT NULL
    )""",
]

# columns added for the NH5 integration -- added to an existing (older) vehicle_events table if missing
ADDED_COLUMNS = {'location': 'VARCHAR(255) NULL', 'camera': 'VARCHAR(120) NULL'}


def admin_users_from_env():
    users = []
    for n in (1, 2):
        u = {
            'username': os.getenv(f'ADMIN{n}_USERNAME'),
            'email': os.getenv(f'ADMIN{n}_EMAIL'),
            'password': os.getenv(f'ADMIN{n}_PASSWORD'),
        }
        if u['username'] and u['email'] and u['password']:
            users.append(u)
    return users


def initialize_database():
    engine, error = db.connect()
    if error is not None:
        print(f"\n[Database Notice] Could not connect to MySQL at {os.getenv('MYSQL_HOST', 'localhost')}:"
              f"{os.getenv('MYSQL_PORT', '3306')} ({error}).")
        print(f'[Database Notice] Using the local SQLite database {db.sqlite_path} instead.\n')

    for statement in (MYSQL_TABLES if engine == 'mysql' else SQLITE_TABLES):
        db.execute(statement)

    existing = db.column_names('vehicle_events')
    for col, col_type in ADDED_COLUMNS.items():
        if col not in existing:
            db.execute(f'ALTER TABLE vehicle_events ADD COLUMN {col} {col_type}')
            print(f'[Database] Added column vehicle_events.{col}')

    # Auto-sync admin users so logins never fail with "invalid password"
    for admin in admin_users_from_env():
        email = admin['email'].strip().lower()
        found = db.query('SELECT id, password FROM users WHERE LOWER(email) = LOWER(%s) LIMIT 1', (email,))
        if not found:
            db.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)',
                       (admin['username'].strip(), email, hash_password(admin['password']), 'admin'))
            print(f"[Database] Auto-seeded admin user: {admin['username']} ({email})")
        elif not check_password(admin['password'], found[0]['password']):
            db.execute('UPDATE users SET username = %s, password = %s WHERE id = %s',
                       (admin['username'].strip(), hash_password(admin['password']), found[0]['id']))
            print(f"[Database] Synchronized updated password for {admin['username']} ({email}) from .env")

    _status.update(connected=True, mock=False, engine=engine,
                   mysql_error=str(error) if error else None)
    return dict(_status)


def get_setting(name, default=None):
    rows = db.query('SELECT value FROM app_settings WHERE name = %s', (name,))
    return rows[0]['value'] if rows else default


def set_setting(name, value):
    db.execute('INSERT INTO app_settings (name, value) VALUES (%s, %s)' + db.upsert_suffix(['name'], ['value']),
               (name, value))


def is_mock_mode():
    return _status['mock']
