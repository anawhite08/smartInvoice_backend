"""
Telemetría ligera del consumo de tokens de Gemini, vía OpenTelemetry (métricas).

No requiere un collector externo: se registra con un exportador de consola (queda en los logs
de Cloud Run) además de las métricas OTel propiamente dichas — listas para engancharse a un
exportador real (OTLP, Cloud Monitoring, etc.) más adelante con solo cambiar el MeterProvider,
sin tocar el resto del código.

Objetivo: poder ver, extracción por extracción, cuántos tokens de entrada consume cada llamada
(separando texto vs. imagen/documento) y cuántos de salida, para estandarizar/monitorear el
gasto de tokens de Gemini a lo largo del tiempo.
"""
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

_reader = PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60_000)
_provider = MeterProvider(metric_readers=[_reader])
metrics.set_meter_provider(_provider)

_meter = metrics.get_meter("smart_invoice.gemini")

_prompt_tokens_counter = _meter.create_counter(
    "gemini.prompt_tokens",
    unit="tokens",
    description="Tokens de entrada consumidos por extracción, por modalidad (texto/imagen)."
)
_output_tokens_counter = _meter.create_counter(
    "gemini.output_tokens",
    unit="tokens",
    description="Tokens de salida generados por Gemini por extracción."
)
_total_tokens_counter = _meter.create_counter(
    "gemini.total_tokens",
    unit="tokens",
    description="Tokens totales (entrada + salida) consumidos por extracción."
)


def record_gemini_usage(usage_metadata, model_name: str) -> None:
    """
    Registra el consumo de tokens de una llamada a Gemini: imprime un resumen legible en los
    logs y lo registra como métricas OpenTelemetry. `usage_metadata` es el objeto que devuelve
    el SDK `google-genai` en `response.usage_metadata`.
    """
    if usage_metadata is None:
        print("⚠️ [Gemini usage] La respuesta no trajo usage_metadata; no se pudo medir el consumo de tokens.")
        return

    prompt_total = usage_metadata.prompt_token_count or 0
    output_total = usage_metadata.candidates_token_count or 0
    grand_total = usage_metadata.total_token_count or (prompt_total + output_total)

    text_in = 0
    image_in = 0
    for detail in (usage_metadata.prompt_tokens_details or []):
        modality = str(getattr(detail, "modality", "")).upper()
        count = detail.token_count or 0
        if "IMAGE" in modality or "DOCUMENT" in modality or "VIDEO" in modality:
            image_in += count
        elif "TEXT" in modality:
            text_in += count
        _prompt_tokens_counter.add(count, {"modality": modality.lower() or "unknown", "model": model_name})

    _output_tokens_counter.add(output_total, {"model": model_name})
    _total_tokens_counter.add(grand_total, {"model": model_name})

    print(
        f"🔢 [Gemini usage] modelo={model_name} · entrada={prompt_total} "
        f"(texto={text_in}, imagen={image_in}) · salida={output_total} · total={grand_total}"
    )
