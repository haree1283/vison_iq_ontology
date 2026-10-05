from flask import Blueprint

from controllers.query_controller import check_ollama_status, parse_natural_language_query

query_routes = Blueprint('query_routes', __name__)

# GET /api/query/ollama-status
query_routes.get('/ollama-status')(check_ollama_status)

# POST /api/query/ai-parse
query_routes.post('/ai-parse')(parse_natural_language_query)
