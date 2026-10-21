import os
from dotenv import load_dotenv

load_dotenv()

USER_DB = os.getenv("userbd")
PASSWORD_DB = os.getenv("passwordbd")
DB_NAME = os.getenv("bd")
DIRECCION = os.getenv("direccion")
# Conexión directa (ej. PostgreSQL en SAP BTP). Si DB_HOST está definido, se ignora Cloud SQL.
DB_HOST = os.getenv("db_host")
DB_PORT = int(os.getenv("db_port", "5432"))
DB_SSLMODE = os.getenv("db_sslmode", "require")
INVOICES_BUCKET_NAME = os.getenv("invoices_bucket_name")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS"
) or os.getenv("google_application_credentials")
TARGET_SERVICE_ACCOUNT = os.getenv("target_service_account")
PROJECT_ID = os.getenv("proyecto_id")
LOCATION = os.getenv("ubicacion")
UNSCANNED_BUCKET_NAME = os.getenv("unscanned_bucket_name", "ordenes_compra")
GEMINI_MODEL = os.getenv("gemini_model", "gemini-3.1-flash-lite")

# Importante: Establecer la variable de entorno para que las librerías de Google la detecten automáticamente
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS
