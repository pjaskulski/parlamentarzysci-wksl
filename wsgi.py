"""Punkt wejścia serwera WSGI, np. Gunicorn."""
if __package__:
    from .app import create_app
else:
    from app import create_app

app = create_app()
