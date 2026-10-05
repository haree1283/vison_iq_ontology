from config.database import db


def find_by_identifier(identifier):
    clean_id = str(identifier or '').strip()
    if not clean_id:
        return None
    field = 'email' if '@' in clean_id else 'username'
    rows = db.query(
        f'SELECT id, username, email, password, role FROM users WHERE LOWER({field}) = LOWER(%s) LIMIT 1',
        (clean_id.lower(),),
    )
    return rows[0] if rows else None


def find_by_id(user_id):
    rows = db.query('SELECT id, username, email, password, role FROM users WHERE id = %s LIMIT 1', (user_id,))
    return rows[0] if rows else None


def upsert_by_email(username, email, password, role='admin'):
    target_email = str(email or '').strip().lower()
    clean_username = str(username or '').strip()
    db.execute(
        'INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)'
        + db.upsert_suffix(['email'], ['username', 'password', 'role']),
        (clean_username, target_email, password, role),
    )


def exists(username=None, email=None):
    """-> 'username' / 'email' when that value is already taken (case-insensitive), else None."""
    if username and db.query('SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1', (username,)):
        return 'username'
    if email and db.query('SELECT id FROM users WHERE LOWER(email) = LOWER(%s) LIMIT 1', (email,)):
        return 'email'
    return None


def create(username, email, password_hash, role='user'):
    db.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)',
               (username, email, password_hash, role))
    return find_by_identifier(email)
