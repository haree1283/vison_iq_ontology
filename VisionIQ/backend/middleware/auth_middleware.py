import os
from functools import wraps
from http.cookies import SimpleCookie

import jwt
from flask import g, jsonify, request

from models import user as User

# Login sets this HttpOnly cookie as well as returning the token: <img>/<video> tags, file downloads and the
# live-camera websocket cannot send an Authorization header, but the browser sends the cookie with all of them.
SESSION_COOKIE = 'viq_session'
SESSION_MAX_AGE = 24 * 3600  # same lifetime as the JWT


def user_for_token(token):
    """The user a JWT belongs to, or None (bad signature, expired, malformed, deleted user, db error)."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, os.environ['JWT_SECRET'], algorithms=['HS256'])
        return User.find_by_id(payload.get('userId'))
    except Exception:  # noqa: BLE001
        return None


def token_from_request():
    scheme, _, token = request.headers.get('Authorization', '').partition(' ')
    if scheme == 'Bearer' and token:
        return token
    return request.cookies.get(SESSION_COOKIE)


def token_from_environ(environ):
    """Same as token_from_request, for plain WSGI code that runs outside a Flask request (NH5Dispatcher)."""
    scheme, _, token = environ.get('HTTP_AUTHORIZATION', '').partition(' ')
    if scheme == 'Bearer' and token:
        return token
    cookie = SimpleCookie()
    try:
        cookie.load(environ.get('HTTP_COOKIE', ''))
    except Exception:  # noqa: BLE001 -- malformed cookie header
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def set_session_cookie(response, token):
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite='Lax',
                        secure=request.is_secure, path='/')
    return response


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='Lax')
    return response


def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = token_from_request()
        if not token:
            return jsonify(success=False, message='Unauthorized.'), 401
        user = user_for_token(token)
        if not user:
            return jsonify(success=False, message='Invalid or expired token.'), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapper
