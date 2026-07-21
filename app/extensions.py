import os
from google.cloud import storage
from google.cloud.sql.connector import Connector
import sqlalchemy
from google.auth import impersonated_credentials
from google.cloud import storage
import google.auth
from .config import USER_DB, PASSWORD_DB, DB_NAME, DIRECCION, TARGET_SERVICE_ACCOUNT, PROJECT_ID, LOCATION
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import documentai
import json

# ---------------------------------------------------------
# Cliente del Modelo de Gemini
# ---------------------------------------------------------
def cliente_gemini():
   # Inicializa Vertex AI
   vertexai.init(project=PROJECT_ID, location=LOCATION)

   # Cargar el modelo de Gemini disponible en Vertex
   model = GenerativeModel("gemini-2.5-flash")  
   return model


# ---------------------------------------------------------
# Cliente de Cloud SQL
# ---------------------------------------------------------

# Conector global 
# Conector SQL 
connector = Connector()

def get_connection():
    # Si detecta que está en Google Cloud (Cloud Run), usa el conector oficial directamente
    if os.getenv('K_SERVICE'):
        print("[CONEXION] Conectando a Cloud SQL usando Connector (Cloud Run)...")
        return connector.connect(
            DIRECCION,
            "pg8000",
            user=USER_DB,
            password=PASSWORD_DB,
            db=DB_NAME,
        )

    # Si estamos en LOCAL, intentamos primero el Proxy local (127.0.0.1)
    # y si falla, intentamos usar el Connector oficial (que también funciona localmente)
    try:
        print("[CONEXION] Intentando conexión a Cloud SQL vía Proxy local (127.0.0.1:5432)...")
        import pg8000
        return pg8000.connect(
            user=USER_DB,
            password=PASSWORD_DB,
            database=DB_NAME,
            host="127.0.0.1",
            port=5432,
            timeout=5 # Timeout corto para no colgar la app si no hay proxy
        )
    except Exception as e:
        print(f"[ADVERTENCIA] No se pudo conectar al Proxy local: {e}")
        print(f"[CONEXION] Reintentando conexión directa a Cloud SQL ({DIRECCION}) usando Connector...")
        try:
            return connector.connect(
                DIRECCION,
                "pg8000",
                user=USER_DB,
                password=PASSWORD_DB,
                db=DB_NAME,
            )
        except Exception as connector_e:
            print(f"[ERROR] Error fatal en la conexión a Cloud SQL: {connector_e}")
            raise connector_e



def get_engine():
    return sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=get_connection)

# ---------------------------------------------------------
# Cliente de Document AI
# ---------------------------------------------------------
def cliente_document_ai():
    """
    Inicializa y retorna el cliente de Document AI y el nombre del recurso.
    """
    client = documentai.DocumentProcessorServiceClient()
    # RESOURCE_NAME sigue el formato: projects/{project}/locations/{location}/processors/{processor}
    # Usamos tus variables importadas de .config
    from .config import PROCESSOR_ID 
    
    resource_name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    
    return client, resource_name

# ---------------------------------------------------------
# Cliente de Storage (impersonadas que sí tienen private key)
# --------------------------------------------------------- 
source_credentials, _ = google.auth.default()
target_credentials = impersonated_credentials.Credentials(
    source_credentials=source_credentials,
    target_principal=TARGET_SERVICE_ACCOUNT,
    target_scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    lifetime=3600,
)

storage_client = storage.Client(credentials=target_credentials)


