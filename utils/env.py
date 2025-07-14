# utils/env.py
from logging import log
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

def get_env():
    return os.getenv("APP_ENV", "dev").lower()