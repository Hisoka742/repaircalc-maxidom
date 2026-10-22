from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maxicalc import __version__
from maxicalc.api.errors import install_error_handlers
from maxicalc.api.middleware import (
    ObservabilityMiddleware,
    RateLimitMiddleware,
    configure_logging,
)
from maxicalc.api.routes import api_v1, ops, router
from maxicalc.api.state import AppState
from maxicalc.api.worktype_routes import wt_router
from maxicalc.config import Settings
from maxicalc.config import settings as default_settings

DESCRIPTION = """
Микросервис умных калькуляторов ремонта для интеграции в maxidom.ru.

* **Количества считает детерминированный движок** (Decimal, округление до упаковок в самом конце).
  ML и LLM только размечают каталог и никогда не участвуют в арифметике.
* Каждая позиция сметы содержит `explain` — ход расчёта на русском.
* Один и тот же запрос при той же версии каталога даёт тот же `estimate_id` и результат.
* Деньги и количества в JSON — строки с точным десятичным значением.
"""

TAGS = [
    {"name": "calc", "description": "Калькуляторы: объект, комната, карточка товара"},
    {"name": "recommend", "description": "Подбор товаров с учётом помещения"},
    {"name": "catalog", "description": "Разметка каталога и очередь проверки"},
    {"name": "estimate", "description": "Экспорт сметы"},
    {"name": "ops", "description": "Служебные"},
]


def create_app(state: AppState | None = None, settings: Settings | None = None) -> FastAPI:
    cfg = settings or default_settings
    configure_logging(cfg.log_json)
    app = FastAPI(title="MaksiDom Smart Repair Calculator", version=__version__,
                  description=DESCRIPTION, openapi_tags=TAGS)
    app.state.maxi = state or AppState.from_settings(cfg)
    install_error_handlers(app)
    # added last = outermost: observability sees rate-limited (429) responses too
    app.add_middleware(RateLimitMiddleware, per_min=cfg.rate_limit_per_min,
                       burst=cfg.rate_limit_burst)
    app.add_middleware(ObservabilityMiddleware)
    # the case's paths: /api/v1/... ; the original /v1/... stay as hidden aliases
    app.include_router(wt_router, prefix="/api")
    app.include_router(wt_router, include_in_schema=False)
    app.include_router(router, prefix="/api")
    app.include_router(router, include_in_schema=False)
    app.include_router(api_v1)
    app.include_router(ops)
    origins = [o.strip() for o in cfg.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=False, max_age=600)
    return app


class _LazyApp:
    """ASGI app that builds the real application on first use (server start).

    Importing this module has no side effects: no catalog is read and no model is loaded
    until the server actually starts (or a test uses `app`)."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None

    def _get(self) -> FastAPI:
        if self._app is None:
            self._app = create_app()
        return self._app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        await self._get()(scope, receive, send)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self._get(), name)


app = _LazyApp()
