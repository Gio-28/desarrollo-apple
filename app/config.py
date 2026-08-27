import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    session_secret: str = os.environ.get("SESSION_SECRET", "")
    allowed_email_domain: str = os.environ.get("ALLOWED_EMAIL_DOMAIN", "appletravel.com.co")

    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    base_url: str = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    dropbox_sign_api_key: str = os.environ.get("DROPBOX_SIGN_API_KEY", "")


settings = Settings()
