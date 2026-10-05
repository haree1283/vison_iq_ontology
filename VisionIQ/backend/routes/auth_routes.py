from flask import Blueprint

from controllers.auth_controller import login, logout, me, signup
from middleware.auth_middleware import require_auth

auth_routes = Blueprint('auth_routes', __name__)

auth_routes.post('/login')(login)
auth_routes.post('/signup')(signup)
auth_routes.get('/me')(require_auth(me))
auth_routes.post('/logout')(logout)
