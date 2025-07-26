# utils/env.py
import os
from dotenv import load_dotenv

# .env laden, wenn vorhanden
load_dotenv()

def get_env() -> dict:
    """Liefert alle gesetzten Umgebungsvariablen aus .env oder System."""
    return dict(os.environ)

def get_env_var(key: str, fallback: str = "") -> str:
    """Liefert einen einzelnen .env-Wert mit optionalem Fallback."""
    return os.getenv(key, fallback)

def validate_env(required_keys=None):
    """Validiert, ob definierte Schlüssel in .env vorhanden sind."""
    if required_keys is None:
        required_keys = ["APP_ENV", "LOG_PATH"]

    missing = [key for key in required_keys if not os.getenv(key)]
    if missing:
        raise EnvironmentError(f"❌ Fehlende Umgebungsvariablen: {', '.join(missing)}")

    print("✅ .env erfolgreich validiert.")
