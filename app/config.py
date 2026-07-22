import os


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
BACKUP_FOLDER = os.path.join(DATA_DIR, "backups")
EXPORT_FOLDER = os.path.join(DATA_DIR, "exportaciones")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
DB_PATH = os.path.join(DATA_DIR, "gastos.db")
MAX_CONTENT_LENGTH = 10 * 1024 * 1024


class Config:
    SECRET_KEY = os.environ.get("GASTOS_SECRET_KEY", "gastos-local-secret")
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    PROJECT_ROOT = PROJECT_ROOT
    DATA_DIR = DATA_DIR
    UPLOAD_FOLDER = UPLOAD_FOLDER
    BACKUP_FOLDER = BACKUP_FOLDER
    EXPORT_FOLDER = EXPORT_FOLDER
