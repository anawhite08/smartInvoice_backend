import os
from dotenv import load_dotenv

load_dotenv()

USER_DB = os.getenv("userbd")
PASSWORD_DB = os.getenv("passwordbd")
DB_NAME = os.getenv("bd")
DIRECCION = os.getenv("direccion")
INVOICES_BUCKET_NAME = os.getenv("invoices_bucket_name")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS"
) or os.getenv("google_application_credentials")
TARGET_SERVICE_ACCOUNT = os.getenv("target_service_account")
PROJECT_ID = os.getenv("proyecto_id")
LOCATION = os.getenv("ubicacion")
UNSCANNED_BUCKET_NAME = os.getenv("unscanned_bucket_name", "ordenes_compra")

# Importante: Establecer la variable de entorno para que las librerías de Google la detecten automáticamente
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS
