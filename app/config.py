import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    session_secret: str = os.environ.get("SESSION_SECRET", "")
    base_url: str = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

    dropbox_sign_api_key: str = os.environ.get("DROPBOX_SIGN_API_KEY", "")

    admin_username: str = os.environ.get("ADMIN_USERNAME", "")
    admin_password: str = os.environ.get("ADMIN_PASSWORD", "")


settings = Settings()
