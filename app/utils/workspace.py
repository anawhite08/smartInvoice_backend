import base64
from email.message import EmailMessage
from email.utils import make_msgid
import datetime

import re
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import mimetypes
import os
import json
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from google.oauth2 import service_account

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


## FUNCIONES PARA MANEJAR GMAIL

## 1. Crear Mensajes
## 1.1. Mensajes de texto
def gmail_create_draft(correo_destino):
  """Create and insert a draft email.
   Print the returned draft's message and id.
   Returns: Draft object, including draft id and message meta data.

  Load pre-authorized user credentials from the environment.
  TODO(developer) - See https://developers.google.com/identity
  for guides on implementing OAuth2 for the application.
  """
  creds, _ = google.auth.default()

  try:
    # create gmail api client
    service = build("gmail", "v1", credentials=creds)

    message = EmailMessage()

    message.set_content("This is automated draft mail")

    message["To"] = correo_destino
    message["From"] = "absibot@abside.com"
    message["Subject"] = "Notificación de Vencimiento"

    # encoded message
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    create_message = {"message": {"raw": encoded_message}}
    # pylint: disable=E1101
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body=create_message)
        .execute()
    )

    print(f'Draft id: {draft["id"]}\nDraft message: {draft["message"]}')

  except HttpError as error:
    print(f"An error occurred: {error}")
    draft = None

  return draft

## 1.2. Mensajes con archivo adjunto
def gmail_create_draft_with_attachment():
  """Create and insert a draft email with attachment.
   Print the returned draft's message and id.
  Returns: Draft object, including draft id and message meta data.

  Load pre-authorized user credentials from the environment.
  TODO(developer) - See https://developers.google.com/identity
  for guides on implementing OAuth2 for the application.
  """
  creds, _ = google.auth.default()

  try:
    # create gmail api client
    service = build("gmail", "v1", credentials=creds)
    mime_message = EmailMessage()

    # headers
    mime_message["To"] = "gduser1@workspacesamples.dev"
    mime_message["From"] = "gduser2@workspacesamples.dev"
    mime_message["Subject"] = "sample with attachment"

    # text
    mime_message.set_content(
        "Hi, this is automated mail with attachment.Please do not reply."
    )

    # attachment
    attachment_filename = "photo.jpg"
    # guessing the MIME type
    type_subtype, _ = mimetypes.guess_type(attachment_filename)
    maintype, subtype = type_subtype.split("/")

    with open(attachment_filename, "rb") as fp:
      attachment_data = fp.read()
    mime_message.add_attachment(attachment_data, maintype, subtype)

    encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

    create_draft_request_body = {"message": {"raw": encoded_message}}
    # pylint: disable=E1101
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body=create_draft_request_body)
        .execute()
    )
    print(f'Draft id: {draft["id"]}\nDraft message: {draft["message"]}')
  except HttpError as error:
    print(f"An error occurred: {error}")
    draft = None
  return draft


def build_file_part(file):
  """Creates a MIME part for a file.

  Args:
    file: The path to the file to be attached.

  Returns:
    A MIME part that can be attached to a message.
  """
  content_type, encoding = mimetypes.guess_type(file)

  if content_type is None or encoding is not None:
    content_type = "application/octet-stream"
  main_type, sub_type = content_type.split("/", 1)
  if main_type == "text":
    with open(file, "rb"):
      msg = MIMEText("r", _subtype=sub_type)
  elif main_type == "image":
    with open(file, "rb"):
      msg = MIMEImage("r", _subtype=sub_type)
  elif main_type == "audio":
    with open(file, "rb"):
      msg = MIMEAudio("r", _subtype=sub_type)
  else:
    with open(file, "rb"):
      msg = MIMEBase(main_type, sub_type)
      msg.set_payload(file.read())
  filename = os.path.basename(file)
  msg.add_header("Content-Disposition", "attachment", filename=filename)
  return msg


# ## 2. Mandar Mensajes
# def gmail_send_message(asunto_correo, cuerpo_correo,correo_destino):
#     """
#     Envía un correo electrónico usando Delegación de Dominio.
#     Funciona en Local (vía archivo JSON) y en Cloud Run (vía Secret Manager).
#     """
#     SCOPES = ['https://www.googleapis.com/auth/gmail.send']
#     creds = None

#     # 1. INTENTAR CARGAR DESDE VARIABLE DE ENTORNO (Cloud Run / Secret Manager)
#     # 'path_service_account' es el nombre que configuraste en tu captura de pantalla
#     service_account_env = os.environ.get('path_service_account')

#     if service_account_env:
#         try:
#             print(">>> Cargando credenciales desde Secret Manager...")
#             info = json.loads(service_account_env)
#             creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
#         except Exception as e:
#             print(f"Error al leer el secreto: {e}")

#     # 2. SI NO HAY VARIABLE, INTENTAR CARGAR DESDE ARCHIVO LOCAL (Tu PC)
#     if not creds:
#         print(">>> Buscando archivo de credenciales local...")
#         base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#         path_local = os.path.join(base_path, 'credenciales', 'absidedoc-28e0072236ab.json')
        
#         if os.path.exists(path_local):
#             creds = service_account.Credentials.from_service_account_file(path_local, scopes=SCOPES)
#         else:
#             return {"error": "No se encontraron credenciales ni en el entorno ni en archivo local."}

#     try:
#         # 3. APLICAR DELEGACIÓN DE DOMINIO
#         # Importante: absibot@abside.com debe estar autorizado en el Admin Console
#         delegated_creds = creds.with_subject('absibot@abside.com')
#         service = build("gmail", "v1", credentials=delegated_creds)

#         # 4. CREAR EL MENSAJE (Cuerpo alineado a la izquierda para evitar sangrías)
#         message = EmailMessage()

#         message["Subject"] = asunto_correo        
#         message.set_content(cuerpo_correo)
#         message["To"] = correo_destino
#         message["From"] = "absibot@abside.com"
        

#         # 5. CODIFICAR Y ENVIAR
#         encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
#         create_message = {"raw": encoded_message}

#         send_message = service.users().messages().send(userId="me", body=create_message).execute()
        
#         print(f'Mensaje enviado con éxito. ID: {send_message["id"]}')
#         return send_message

#     except HttpError as error:
#         print(f"Ocurrió un error en la API de Gmail: {error}")
#         return {"error": str(error)}
#     except Exception as e:
#         print(f"Ocurrió un error inesperado: {e}")
#         return {"error": str(e)}

def gmail_send_message(asunto_correo, cuerpo_correo, correo_destino):
    """
    Envía un correo electrónico usando Delegación de Dominio.
    Corregido para manejar escapes de caracteres en Cloud Run.
    """
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']
    creds = None

    # 1. CARGAR DESDE VARIABLE DE ENTORNO (Cloud Run / Secret Manager)
    service_account_env = os.environ.get('path_service_account')

    if service_account_env:
        try:
            print(">>> Cargando credenciales desde Secret Manager...")
            info = json.loads(service_account_env)
            
            # --- SOLUCIÓN AL ERROR DE FIRMA (Invalid Signature) ---
            # Si la llave viene con saltos de línea escapados (\\n), los convertimos a reales (\n)
            if 'private_key' in info:
                info['private_key'] = info['private_key'].replace('\\n', '\n')
            # -------------------------------------------------------

            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            print(f"Error al procesar el JSON del secreto: {e}")

    # 2. INTENTO LOCAL (Si lo anterior falla)
    if not creds:
        print(">>> Buscando archivo de credenciales local...")
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path_local = os.path.join(base_path, 'credenciales', 'absidedoc-28e0072236ab.json')
        
        if os.path.exists(path_local):
            creds = service_account.Credentials.from_service_account_file(path_local, scopes=SCOPES)
        else:
            return {"error": "No se encontraron credenciales válidas."}

    # Ruta del logo
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logo_path = os.path.join(base_path, 'imagenes', 'LOGO-Absidocs-SC-1.jpg')

    try:
        # 3. DELEGACIÓN DE DOMINIO
        delegated_creds = creds.with_subject('absibot@abside.com')
        service = build("gmail", "v1", credentials=delegated_creds)

        # --- 4. LIMPIEZA DE TEXTO (SOLUCIÓN A SALTOS DE LÍNEA) ---
        
        # 4.1 Limpiar Asunto (Convertir todo a una sola línea)
        asunto_limpio = " ".join(asunto_correo.split())

        # 4.2 Limpiar Cuerpo (Unir párrafos, mantener saltos dobles)
        # Normalizamos saltos de línea
        texto = cuerpo_correo.replace('\r', '')
        # Protegemos los saltos dobles (párrafos reales)
        texto = texto.replace('\n\n', '[[DOUBLE_NL]]')
        # Los saltos simples los convertimos en espacio (unimos las líneas cortadas)
        texto = texto.replace('\n', ' ')
        # Restauramos saltos dobles
        texto = texto.replace('[[DOUBLE_NL]]', '\n\n')
        # Eliminamos espacios múltiples accidentales
        cuerpo_limpio = re.sub(r' +', ' ', texto).strip()
        # -------------------------------------------------------

        # --- 5. CREAR EL MENSAJE ---
        message = EmailMessage()
        message["Subject"] = asunto_limpio        
        message["To"] = correo_destino
        message["From"] = "absibot@abside.com"

        # 5.1 Cuerpo en Texto Plano (Fallback)
        message.set_content(cuerpo_limpio)

        # 5.2 Cuerpo en HTML con Diseño
        logo_cid = make_msgid()
        
        # Detectar enlaces y convertirlos en tags <a> (Hacerlo antes de insertar tags HTML para evitar capturarlos)
        # Usamos un regex que se detiene en espacios o caracteres que no suelen ser parte de una URL al final de una frase
        cuerpo_con_links = re.sub(r'(https?://[^\s<>"]+)', r'<a href="\1" style="color: #0056b3; font-weight: bold;">\1</a>', cuerpo_limpio)

        # Convertimos saltos de línea a HTML
        cuerpo_html_content = cuerpo_con_links.replace('\n\n', '</p><p>').replace('\n', '<br>')
        cuerpo_html_content = f"<p>{cuerpo_html_content}</p>"

        anio_actual = datetime.datetime.now().year
        
        html_template = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden; background-color: #ffffff; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <div style="background-color: #ffffff; padding: 25px; text-align: center; border-bottom: 3px solid #0056b3;">
                    <img src="cid:{logo_cid[1:-1]}" alt="Absidocs" style="max-width: 200px; height: auto;">
                </div>
                <div style="padding: 40px;">
                    <h2 style="color: #0056b3; margin-top: 0; font-size: 22px; border-bottom: 1px solid #eee; padding-bottom: 10px;">
                        Notificación del Sistema
                    </h2>
                    <div style="font-size: 15px; color: #444; text-align: justify;">
                        {cuerpo_html_content}
                    </div>
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 13px; color: #888;">
                        <p>Si tiene alguna duda, por favor póngase en contacto con el administrador del sistema.</p>
                    </div>
                </div>
                <div style="background-color: #f4f7f9; padding: 20px; text-align: center; font-size: 12px; color: #777;">
                    Este es un mensaje automático generado por <strong>Absidocs</strong>.<br>
                    &copy; {anio_actual} Abside - Todos los derechos reservados.
                </div>
            </div>
        </body>
        </html>
        """

        message.add_alternative(html_template, subtype='html')

        # 5.3 Incrustar Imagen del Logo
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as img:
                message.get_payload()[1].add_related(
                    img.read(), 
                    maintype='image', 
                    subtype='jpeg', 
                    cid=logo_cid
                )

        # 6. CODIFICAR Y ENVIAR
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}

        send_message = service.users().messages().send(userId="me", body=create_message).execute()
        
        print(f'Mensaje enviado con éxito. ID: {send_message["id"]}')
        return send_message

    except HttpError as error:
        # Si aquí te da 403, revisa que la API de Gmail esté habilitada en el proyecto de Cloud Run
        print(f"Error API Gmail: {error}")
        return {"error": str(error)}
    except Exception as e:
        print(f"Error inesperado: {e}")
        return {"error": str(e)}



######################### DRIVE #########################

# ---------------------------------------------------------
# Cliente de DRIVE
# --------------------------------------------------------- 

import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

def get_drive_service():
    """Inicializa el servicio de Drive optimizado para Cloud Run y Local."""
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = None

    # 1. PRIORIDAD: Intentar cargar desde la variable de entorno (Cloud Run / Secret Manager)
    service_account_env = os.environ.get('path_service_account')
    
    if service_account_env:
        try:
            print(">>> Detectada variable 'path_service_account'. Cargando...")
            info = json.loads(service_account_env)
            if 'private_key' in info:
                info['private_key'] = info['private_key'].replace('\\n', '\n')
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            print(f">>> Error procesando JSON de la variable de entorno: {e}")

    # 2. SEGUNDA OPCIÓN: Cargar local (Solo si no estamos en Cloud Run)
    if not creds:
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            path_local = os.path.join(base_path, 'credenciales', 'smart-order-creation-a7b97f3737ed.json')
            
            if os.path.exists(path_local):
                print(f">>> Cargando credenciales locales desde: {path_local}")
                creds = service_account.Credentials.from_service_account_file(path_local, scopes=SCOPES)
                return build("drive", "v3", credentials=creds)
            else:
                print(f">>> ADVERTENCIA: No se encontró archivo local en {path_local}")
        except Exception as e:
            print(f">>> Error cargando archivo local: {e}")

    # 3. SI LLEGAMOS AQUÍ, NADA FUNCIONÓ
    raise Exception("No se pudieron obtener credenciales de Google Drive (Entorno o Local).")

def list_files_in_shared_folder(folder_id):
    service = get_drive_service()
    
    query = f"'{folder_id}' in parents and trashed = false"
    
    # Añadimos 'webViewLink' a los campos solicitados
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, webViewLink, createdTime)"
    ).execute()
    
    return results.get('files', [])

def upload_to_folder(folder_id, file_path, file_name):
    """Sube un archivo local a la carpeta de Drive y retorna ID y Link."""
    try:
        service = get_drive_service()
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)
        
        # Agregamos webViewLink a los fields
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return {
            "id": file.get('id'),
            "link": file.get('webViewLink')
        }
    except Exception as e:
        print(f"Error subiendo a Drive: {e}")
        return None

def download_file_from_drive(file_id):
    """
    Descarga el contenido de un archivo de Drive dado su ID.
    """
    service = get_drive_service()
    
    # 1. Crear la solicitud para obtener los bytes del archivo
    request = service.files().get_media(fileId=file_id)
    
    # 2. Preparar el buffer en memoria para recibir los datos
    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)
    
    # 3. Realizar la descarga por partes (chunks)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"Descarga en progreso: {int(status.progress() * 100)}%")

    # 4. Volver al principio del stream para poder leerlo
    file_stream.seek(0)
    return file_stream.read(), file_stream # Retorna los bytes

def create_drive_folder(folder_name, parent_folder_id=None):
    """
    Crea una nueva carpeta en Google Drive.
    Retorna el ID de la carpeta creada.
    """
    try:
        service = get_drive_service()
        
        # Metadatos de la carpeta
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # Si queremos que esté dentro de otra carpeta específica
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]

        # Crear la carpeta
        folder = service.files().create(
            body=file_metadata,
            fields='id, webViewLink'
        ).execute()
        
        print(f"Carpeta creada con éxito. ID: {folder.get('id')}")
        return folder # Retorna el diccionario con ID y Link
        
    except Exception as e:
        print(f"Error al crear carpeta: {e}")
        return {"error": str(e)}


def get_folder_id_by_name(folder_name, parent_id):
    """
    Busca una carpeta por nombre dentro de un padre específico.
    """
    try:
        service = get_drive_service()
        
        # Filtramos por nombre, tipo carpeta y que el padre sea el root_id pasado
        query = (
            f"name = '{folder_name}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false and "
            f"'{parent_id}' in parents"
        )
        
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            return None
            
        return items[0]['id']
        
    except Exception as e:
        print(f"Error buscando carpeta '{folder_name}': {e}")
        return None

def get_or_create_subfolder(folder_name, root_id):
    """
    Busca la carpeta dentro del root_id. Si no existe, la crea.
    """
    # 1. Intentar buscarla
    folder_id = get_folder_id_by_name(folder_name, root_id)
    
    if folder_id:
        print(f">>> Carpeta encontrada: {folder_name} (ID: {folder_id})")
        return folder_id
    
    # 2. Si no existe, crearla (Usando tu función create_drive_folder)
    print(f">>> Carpeta no encontrada. Creando '{folder_name}' dentro de {root_id}...")
    new_folder = create_drive_folder(folder_name, root_id)
    
    # Si create_drive_folder devuelve un dict con 'id'
    return new_folder.get('id') if isinstance(new_folder, dict) else new_folder


def delete_drive_folder(folder_id):
    """
    Elimina permanentemente una carpeta y todo su contenido.
    """
    try:
        service = get_drive_service()
        
        # El método delete borra el archivo/folder permanentemente
        service.files().delete(fileId=folder_id).execute()
        
        print(f">>> Carpeta {folder_id} eliminada permanentemente.")
        return {"status": "success", "message": "Carpeta eliminada para siempre."}
        
    except Exception as e:
        print(f"Error al eliminar carpeta: {e}")
        return {"status": "error", "message": str(e)}



def move_folder_to_trash(folder_id):
    """
    Mueve una carpeta a la papelera (Trash).
    """
    try:
        service = get_drive_service()
        
        # Se usa 'update' para cambiar el estado 'trashed' a True
        service.files().update(
            fileId=folder_id, 
            body={'trashed': True}
        ).execute()
        
        print(f">>> Carpeta {folder_id} movida a la papelera.")
        return {"status": "success", "message": "Movido a la papelera."}
        
    except Exception as e:
        print(f"Error al mover a papelera: {e}")
        return {"status": "error", "message": str(e)}