import os
import re
import time

import jwt
from flask import g, jsonify, request

from config.database import check_password, hash_password
from middleware.auth_middleware import clear_session_cookie, set_session_cookie, token_from_request
from models import user as User



def public_user(user):
    return {'id': str(user['id']), 'username': user['username'], 'email': user['email'], 'role': user['role']}


def create_token(user):
    now = int(time.time())
    payload = {'userId': str(user['id']), 'role': user['role'], 'iat': now, 'exp': now + 24 * 3600}
    return jwt.encode(payload, os.environ['JWT_SECRET'], algorithm='HS256')


def login():
    body = request.get_json(silent=True) or {}
    login_identifier = str(body.get('identifier') or body.get('email') or body.get('username') or '').strip()
    clean_password = str(body.get('password') or '').strip()

    if not login_identifier or not clean_password:
        return jsonify(success=False, message='Email/username and password are required.'), 400

    try:
        user = User.find_by_identifier(login_identifier)
        if not user:
            print(f'[Auth] Login failed: User "{login_identifier}" not found in database.')
            return jsonify(success=False, message='Invalid email/username or password.'), 401

        # (the Node backend also accepted shared "team passwords" for any account -- a backdoor, removed)
        password_match = check_password(clean_password, user['password'])

        if not password_match:
            print(f'[Auth] Login failed: Incorrect password for user "{login_identifier}".')
            return jsonify(success=False, message='Invalid email/username or password.'), 401

        print(f"[Auth] Login successful for user \"{user['username']}\" ({user['email']})")
        token = create_token(user)
        return set_session_cookie(jsonify(success=True, message='Login successful', token=token,
                                          user=public_user(user)), token)
    except Exception as err:  # noqa: BLE001
        print('[Auth] Error during login:', err)
        return jsonify(success=False, message='An error occurred during login.'), 500


USERNAME_RE = re.compile(r'^[A-Za-z0-9._-]{3,30}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD_LENGTH = 8


def signup_enabled():
    return os.getenv('ALLOW_SIGNUP', 'true').strip().lower() != 'false'


def signup():
    """Self-service account creation; logs the new user in (same response shape as login)."""
    if not signup_enabled():
        return jsonify(success=False, message='Sign up is disabled. Ask an administrator for an account.'), 403

    body = request.get_json(silent=True) or {}
    username = str(body.get('username') or '').strip()
    email = str(body.get('email') or '').strip().lower()
    password = str(body.get('password') or '').strip()  # login trims the password too

    if not username or not email or not password:
        return jsonify(success=False, message='Username, email and password are required.'), 400
    if not USERNAME_RE.match(username):
        return jsonify(success=False, message='Username must be 3-30 characters: letters, numbers, dot, dash or underscore.'), 400
    if len(email) > 255 or not EMAIL_RE.match(email):
        return jsonify(success=False, message='Enter a valid email address.'), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify(success=False, message=f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'), 400
    if len(password.encode('utf-8')) > 72:
        return jsonify(success=False, message='Password must be at most 72 bytes.'), 400

    try:
        taken = User.exists(username=username, email=email)
        if taken:
            return jsonify(success=False, message=f'An account with this {taken} already exists.'), 409
        role = os.getenv('SIGNUP_ROLE', 'user').strip() or 'user'
        try:
            user = User.create(username, email, hash_password(password), role)
        except Exception:  # noqa: BLE001 -- unique constraint hit by a concurrent sign up
            taken = User.exists(username=username, email=email)
            if taken:
                return jsonify(success=False, message=f'An account with this {taken} already exists.'), 409
            raise
        print(f"[Auth] New account created: \"{user['username']}\" ({user['email']}), role {user['role']}")
        token = create_token(user)
        return set_session_cookie(jsonify(success=True, message='Account created', token=token,
                                          user=public_user(user)), token), 201
    except Exception as err:  # noqa: BLE001
        print('[Auth] Error during sign up:', err)
        return jsonify(success=False, message='An error occurred while creating the account.'), 500


def me():
    # also (re)sets the session cookie, so a browser that logged in before the cookie existed gets one
    return set_session_cookie(jsonify(success=True, user=public_user(g.user)), token_from_request())


def logout():
    return clear_session_cookie(jsonify(success=True, message='Logged out'))
