import os
import firebase_admin
from firebase_admin import credentials, auth

def inicializar_firebase():
    # Buscamos una variable de entorno con la ruta del JSON
    ruta_credenciales = os.getenv("FIREBASE_CREDENTIALS_PATH")

    if ruta_credenciales and os.path.exists(ruta_credenciales):
        # Estamos en LOCAL: Usamos el archivo JSON
        cred = credentials.Certificate(ruta_credenciales)
        firebase_admin.initialize_app(cred)
        print("Firebase inicializado con JSON local.")
    else:
        # Estamos en CLOUD RUN: Usamos las credenciales por defecto de Google
        firebase_admin.initialize_app()
        print("Firebase inicializado con Application Default Credentials.")

inicializar_firebase()

def delete_firebase_user(correo):
    try:
        # Si no hay correo, evitamos el error de auth
        if not correo:
            return False, "No se proporcionó correo para Firebase"
            
        firebase_user = auth.get_user_by_email(correo)
        auth.delete_user(firebase_user.uid)
        return True, f"Usuario {firebase_user.uid} eliminado de Firebase"
    except auth.UserNotFoundError:
        return False, "Usuario no encontrado en Firebase"
    except Exception as e:
        return False, f"Error en Firebase: {str(e)}"