# utils/logger.py
import logging
from pathlib import Path
from utils.env import get_env

# Hole den Pfad aus der Umgebung oder nutze Standard
log_path_str = get_env("LOG_PATH", "log/import.log")
LOG_PATH = Path(log_path_str)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("[%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)

def log_import(msg, level="info"):
    level = level.lower()
    if level == "debug":
        logging.debug(msg)
    elif level == "warning":
        logging.warning(msg)
    elif level == "error":
        logging.error(msg)
    else:
        logging.info(msg)

def get_log_path():
    return LOG_PATH
