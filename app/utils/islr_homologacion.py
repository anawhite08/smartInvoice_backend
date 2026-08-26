"""
Homologación automática de ISLR por ítem — Caso 1 extendido.

Cuando un proveedor tiene VARIOS códigos ISLR posibles (según `proveedor_impuestos`, ver
`app/utils/cloudsql.get_impuestos_permitidos`), no alcanza con un solo campo de texto libre a
nivel de documento (`tipo_servicio_islr`): hay que homologar la descripción de CADA ítem contra
los códigos candidatos, en el contexto fiscal venezolano. Esto se resuelve con una segunda
llamada a Gemini (texto plano, sin reenviar el documento — el modelo ya trabaja solo con las
descripciones que la extracción principal ya sacó del papel).

Cuando el proveedor solo tiene UN código permitido, no hace falta nada de esto: se resuelve
enteramente en el frontend (código único + monto = % × subtotal), sin gastar una llamada a
Gemini — ver `construirSeleccionIslrInicial` en el frontend (`src/utils/businessRules.ts`).
"""
import json
import re

# Letras cortas para referenciar cada candidato en el prompt — más confiable que pedirle a
# Gemini que repita un UUID exacto en la respuesta.
_LETRAS = [chr(ord("A") + i) for i in range(26)]


def resolver_candidatos_islr(id_proveedor: str | None, impuestos: list) -> list:
    """
    Códigos ISLR candidatos para homologar. Si el proveedor tiene códigos ISLR permitidos
    configurados (tabla proveedor_impuestos, importada del Excel real del cliente), se usan
    esos. Si no tiene ninguno configurado (proveedor esporádico — ej. el bloque de terceros
    de Magnet Agency, que siempre resuelve al centinela — o un proveedor real que todavía no
    está cargado en el Excel), se cae al catálogo ISLR completo: mismo criterio "sugerir de
    más, nunca bloquear" que el resto del sistema — Gemini igual puede dejar ítems sin asignar
    si no está razonablemente seguro.
    """
    from .cloudsql import get_impuestos_permitidos

    catalogo_islr = [t for t in impuestos if t.get("tipo_impuesto") == "ISLR"]
    if not id_proveedor:
        return catalogo_islr

    permitidos = [t for t in get_impuestos_permitidos(id_proveedor) if t.get("tipo_impuesto") == "ISLR"]
    return permitidos if permitidos else catalogo_islr


def homologar_items_islr(gemini_client, model: str, items: list, candidatos: list) -> dict:
    """
    Homologa cada ítem (descripción) contra los códigos ISLR candidatos vía una llamada de
    texto plano a Gemini. Agrupa el resultado por código resuelto, sumando el monto de los
    ítems que le tocaron a cada uno — mismo criterio de "agrupar y sumar" que ya usa
    `agruparHojaRutaPorCeco` en el frontend para Centro de Costo.

    Nunca lanza: cualquier fallo (red, parseo) devuelve el resultado vacío, para que la
    extracción principal nunca se vea bloqueada por esta homologación adicional — el analista
    siempre puede seguir marcando ISLR a mano, como ya funcionaba antes de esto.

    Devuelve: {"grupos": [{"id_impuesto_islr": str, "monto": float, "conceptos": [str, ...]}],
               "sin_asignar": [str, ...]}
    """
    vacio = {"grupos": [], "sin_asignar": []}
    if not items or len(candidatos) < 2:
        return vacio

    candidatos_por_letra = dict(zip(_LETRAS, candidatos))
    lineas_candidatos = "\n".join(
        f'{letra}) {c.get("descripcion_impuesto")} ({c.get("porcentaje")}%)'
        for letra, c in candidatos_por_letra.items()
    )
    lineas_items = "\n".join(
        f'{idx + 1}) "{it.get("descripcion_articulo") or it.get("descripcion") or ""}" '
        f'- monto {it.get("importe_posicion") or it.get("monto") or 0}'
        for idx, it in enumerate(items)
    )

    prompt = f"""Eres un clasificador fiscal experto en retenciones de ISLR en Venezuela.

Candidatos posibles (código de retención ISLR):
{lineas_candidatos}

Ítems de la factura:
{lineas_items}

Para CADA ítem, decide cuál candidato corresponde según la naturaleza del servicio/producto
descrito, en el contexto de la normativa fiscal venezolana. Si ningún candidato corresponde con
razonable seguridad, usa null — NUNCA inventes ni fuerces una clasificación dudosa.

Responde ÚNICAMENTE con un array JSON, sin bloques de código ni texto adicional, con esta forma
exacta: [{{"item": 1, "candidato": "A"}}, {{"item": 2, "candidato": null}}, ...] — un elemento
por cada ítem de la lista, en el mismo orden."""

    try:
        response = gemini_client.models.generate_content(model=model, contents=[prompt])
        raw_text = response.text.strip()
        clean_text = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()
        resultado = json.loads(clean_text)
    except Exception as e:
        print(f"⚠️ Homologación ISLR por ítem falló, se omite (el analista puede marcar ISLR a mano): {e}")
        return vacio

    grupos_por_id: dict[str, dict] = {}
    sin_asignar: list[str] = []

    for entrada in resultado if isinstance(resultado, list) else []:
        try:
            idx = int(entrada.get("item")) - 1
            letra = entrada.get("candidato")
        except (TypeError, ValueError, AttributeError):
            continue
        if idx < 0 or idx >= len(items):
            continue
        item = items[idx]
        descripcion = item.get("descripcion_articulo") or item.get("descripcion") or ""
        monto = float(item.get("importe_posicion") or item.get("monto") or 0)

        candidato = candidatos_por_letra.get(letra) if letra else None
        if not candidato:
            if descripcion:
                sin_asignar.append(descripcion)
            continue

        id_impuesto = candidato.get("id_impuesto")
        if id_impuesto not in grupos_por_id:
            grupos_por_id[id_impuesto] = {"id_impuesto_islr": id_impuesto, "monto": 0.0, "conceptos": []}
        grupos_por_id[id_impuesto]["monto"] += monto
        if descripcion:
            grupos_por_id[id_impuesto]["conceptos"].append(descripcion)

    return {"grupos": list(grupos_por_id.values()), "sin_asignar": sin_asignar}
