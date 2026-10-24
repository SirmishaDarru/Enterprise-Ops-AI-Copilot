import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "local-test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault("APP_ENV", "test")
