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

def actualizar_firebase_user(uid, email_actual, email=None, display_name=None):
    """
    Actualiza correo y/o nombre visible en Firebase Auth. Busca primero por uid (los usuarios
    nuevos comparten UUID con la BD) y, si no existe, por el correo actual (usuarios antiguos
    con UID distinto). Devuelve (firebase_uid, error).
    """
    try:
        try:
            firebase_user = auth.get_user(uid)
        except auth.UserNotFoundError:
            firebase_user = auth.get_user_by_email(email_actual)

        cambios = {}
        if email is not None:
            cambios["email"] = email
        if display_name is not None:
            cambios["display_name"] = display_name
        if cambios:
            auth.update_user(firebase_user.uid, **cambios)
        return firebase_user.uid, None
    except auth.UserNotFoundError:
        return None, "Usuario no encontrado en Firebase"
    except auth.EmailAlreadyExistsError:
        return None, f"El correo '{email}' ya está registrado en Firebase"
    except Exception as e:
        return None, str(e)

def crear_firebase_user(email, nombre, apellido, uid=None):
    import secrets
    try:
        # Generar una contraseña temporal aleatoria (el usuario nunca la verá)
        temp_password = secrets.token_urlsafe(16)

        # Si se pasa uid, lo inyectamos; de lo contrario Firebase generará uno
        user_args = {
            "email": email,
            "password": temp_password,
            "display_name": f"{nombre} {apellido}".strip()
        }
        if uid:
            user_args["uid"] = uid

        user = auth.create_user(**user_args)

        print(f"✅ Usuario Firebase creado: {user.uid} ({email})")
        return user, None
    except Exception as e:
        return None, str(e)