"""Punkt wejścia serwera WSGI, np. Gunicorn."""
if __package__:
    from .app import create_app
else:
    from app import create_app

app = create_app()

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=0,
    x_prefix=1,
)
