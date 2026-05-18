import os
from dotenv import load_dotenv

load_dotenv()

USER_DB = os.getenv("userbd")
PASSWORD_DB = os.getenv("passwordbd")
DB_NAME = os.getenv("bd")
DIRECCION = os.getenv("direccion")
UNSCANNED_BUCKET_NAME = os.getenv("ordenes_compra_bucket_name")
CADENAS_LOGO_BUCKET_NAME = os.getenv("cadenas_logo_bucket_name")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("google_application_credentials")
TARGET_SERVICE_ACCOUNT = os.getenv("target_service_account")
PROJECT_ID = os.getenv("proyecto_id")
LOCATION = os.getenv("ubicacion")

# Importante: Establecer la variable de entorno para que las librerías de Google la detecten automáticamente
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

import os

# Ensure these three are defined in this file:
JSONL_FILE = os.getenv("JSONL_FILE", "default_filename.jsonl")
CLEAN_BUCKET_NAME = os.getenv("CLEAN_BUCKET_NAME", "your-clean-bucket-name")
UNSCANNED_BUCKET_NAME = os.getenv("UNSCANNED_BUCKET_NAME", "your-unscanned-bucket-name")



