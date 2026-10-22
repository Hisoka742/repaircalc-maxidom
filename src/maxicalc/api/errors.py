"""Uniform Russian error bodies: {"error": {"code", "message", "details"}}."""
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()


def _msg(err: dict[str, Any]) -> str:
    t = err.get("type", "")
    ctx = err.get("ctx") or {}
    table = {
        "missing": "Обязательное поле",
        "greater_than": f"Значение должно быть больше {ctx.get('gt')}",
        "greater_than_equal": f"Значение должно быть не меньше {ctx.get('ge')}",
        "less_than": f"Значение должно быть меньше {ctx.get('lt')}",
        "less_than_equal": f"Значение не должно превышать {ctx.get('le')}",
        "int_parsing": "Нужно целое число",
        "int_type": "Нужно целое число",
        "decimal_parsing": "Нужно число",
        "decimal_type": "Нужно число",
        "float_parsing": "Нужно число",
        "string_type": "Нужна строка",
        "bool_parsing": "Нужно значение да/нет",
        "list_type": "Нужен список",
        "dict_type": "Нужен объект",
        "json_invalid": "Некорректный JSON",
        "too_short": f"Слишком мало элементов (минимум {ctx.get('min_length')})",
        "too_long": f"Слишком много элементов (максимум {ctx.get('max_length')})",
        "string_too_short": f"Слишком короткая строка (минимум {ctx.get('min_length')})",
        "string_too_long": f"Слишком длинная строка (максимум {ctx.get('max_length')})",
        "literal_error": f"Допустимые значения: {ctx.get('expected')}",
        "extra_forbidden": "Лишнее поле",
    }
    if t in table:
        return table[t]
    if t == "value_error":
        return str(err.get("msg", "")).removeprefix("Value error, ")
    return f"Некорректное значение ({err.get('msg', t)})"


def error_body(
    code: str, message: str, details: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or []}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]),
             "message": _msg(e)}
            for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", "Некорректные параметры запроса",
                                       details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        names = {404: "Не найдено", 405: "Метод не поддерживается",
                 429: "Слишком много запросов", 501: "Не реализовано"}
        generic = names.get(exc.status_code, "Ошибка запроса")
        msg = exc.detail if isinstance(exc.detail, str) and exc.detail != "Not Found" else generic
        return JSONResponse(error_body(f"http_{exc.status_code}", msg),
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        # the engine/service layers raise ValueError with Russian, user-facing messages
        log.info("invalid_request", error=str(exc))
        return JSONResponse(error_body("invalid_request", str(exc)), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error=repr(exc), exc_info=exc)
        return JSONResponse(error_body("internal_error", "Внутренняя ошибка сервиса"),
                            status_code=500)
