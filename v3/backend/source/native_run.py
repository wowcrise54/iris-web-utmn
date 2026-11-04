from app import asgi_app as app
from app.observability_logging import LoggingMiddleware, configure_logging

# Uvicorn configures its own handlers before importing the application.
configure_logging()
app = LoggingMiddleware(app)
