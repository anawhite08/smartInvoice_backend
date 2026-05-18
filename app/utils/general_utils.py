import time
import json
import re

def retry_function(func, retries, delay, backoff_factor, clean_bucket_name, quarantined_bucket_name, file_id):
    """Retries a function with exponential backoff if it raises an error or returns 'not_found'."""
    attempts = 0

    while attempts < retries:
        try:
            result = func(clean_bucket_name, quarantined_bucket_name, file_id)

            # 🔁 Si devuelve 'not_found' y aún hay intentos disponibles
            if result == "not_found" and attempts < retries - 1:
                print(f"Attempt {attempts + 1}: result='not_found'. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= backoff_factor
                attempts += 1
                continue  # vuelve a intentar

            # ✅ Si fue exitoso o es el último intento
            return result

        except Exception as e:
            attempts += 1
            if attempts < retries:
                print(f"Attempt {attempts} failed with error: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                print("❌ All retries failed. Raising last exception.")
                raise  # re-lanza la última excepción si todos fallan

def safe_value(v):
    """Convierte RepeatedComposite / Struct / Protobuf en valores JSON válidos."""
    if hasattr(v, "to_dict"):
        return v.to_dict()            # Para Struct o objetos complejos
    if isinstance(v, (list, tuple)):
        return [safe_value(x) for x in v]
    if "RepeatedComposite" in str(type(v)):
        return [safe_value(x) for x in v]
    return v

def extraer_json_de_respuesta(texto_raw: str):
    """
    Extrae el primer bloque JSON válido dentro de un string.
    Devuelve None si no lo encuentra.
    """
    try:
        # Buscar cualquier bloque { .... }
        match = re.search(r'\{.*\}', texto_raw, re.DOTALL)
        if not match:
            return None
        bloque = match.group(0)

        return json.loads(bloque)
    except Exception:
        return None