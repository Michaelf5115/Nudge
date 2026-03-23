"""
Root conftest.py — sets required environment variables before Django settings load.
Allows pytest to run without a local .env file (useful in CI/CD pipelines).

For `python manage.py test`, ensure a .env file exists with at minimum:
    SECRET_KEY=<your-secret-key>
    DB_NAME=nudge_test   (or your test DB name)
"""
import os

os.environ.setdefault("SECRET_KEY", "test-only-unsafe-secret-key-do-not-use-in-production")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("DB_NAME", "nudge_db")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
