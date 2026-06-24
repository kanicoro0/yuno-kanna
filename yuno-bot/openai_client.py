from openai import AsyncOpenAI

from config import (
    OPENAI_API_KEY,
    OPENAI_FALLBACK_MODEL,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_TIMEOUT,
)


openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
TEMPERATURE_UNSUPPORTED_MODELS = set()


async def oa_chat(
    messages,
    *,
    temperature=OPENAI_TEMPERATURE,
    timeout=OPENAI_TIMEOUT,
    json_mode_hint=False,
):
    """OpenAI呼び出しとモデル互換性フォールバックを共通化する。"""

    def _is_bad_request(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
        error_name = type(error).__name__
        return status_code == 400 or error_name in {"BadRequestError", "InvalidRequestError"}

    def _is_temperature_bad_request(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code != 400:
            return False

        param = getattr(error, "param", None)
        body = getattr(error, "body", None)
        if param is None and isinstance(body, dict):
            error_body = body.get("error", body)
            if isinstance(error_body, dict):
                param = error_body.get("param")

        error_message = f"{getattr(error, 'message', '')} {error}"
        return "temperature" in error_message.lower() or "temperature" in str(param).lower()

    def _mark_temperature_unsupported(model: str):
        if model not in TEMPERATURE_UNSUPPORTED_MODELS:
            TEMPERATURE_UNSUPPORTED_MODELS.add(model)
            print(
                f"OpenAI: temperature非対応モデルを検出。以後temperatureなしで呼び出す "
                f"(model={model})"
            )

    def _create_kwargs(model: str, json_mode: bool, include_temperature: bool):
        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if include_temperature and model not in TEMPERATURE_UNSUPPORTED_MODELS:
            kwargs["temperature"] = temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    async def _request(model: str, json_mode: bool, include_temperature: bool):
        return await openai_client.chat.completions.create(
            **_create_kwargs(model, json_mode, include_temperature)
        )

    async def _normal_call(model: str, include_temperature: bool = True):
        try:
            return await _request(model, False, include_temperature)
        except Exception as normal_error:
            if not include_temperature or not _is_temperature_bad_request(normal_error):
                raise
            _mark_temperature_unsupported(model)
            return await _request(model, False, False)

    async def _call(model: str, json_mode: bool):
        if not json_mode:
            return await _normal_call(model)

        try:
            return await _request(model, True, True)
        except Exception as json_error:
            if _is_temperature_bad_request(json_error):
                _mark_temperature_unsupported(model)
                try:
                    return await _request(model, True, False)
                except Exception as json_without_temperature_error:
                    if not _is_bad_request(json_without_temperature_error):
                        raise
                    print(
                        f"OpenAI JSON modeを通常モードへフォールバック "
                        f"(model={model}, temperatureなし): "
                        f"{json_without_temperature_error!r}"
                    )
                    return await _normal_call(model, include_temperature=False)

            if not _is_bad_request(json_error):
                raise
            print(
                f"OpenAI JSON modeを通常モードへフォールバック "
                f"(model={model}): {json_error!r}"
            )
            return await _normal_call(model)

    try:
        return await _call(OPENAI_MODEL, json_mode_hint)
    except Exception as primary_error:
        if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL:
            try:
                return await _call(OPENAI_FALLBACK_MODEL, json_mode_hint)
            except Exception as fallback_error:
                raise RuntimeError(
                    f"primary({OPENAI_MODEL})→{primary_error!r}; "
                    f"fallback({OPENAI_FALLBACK_MODEL})→{fallback_error!r}"
                )
        raise
