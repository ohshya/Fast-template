from types import ModuleType

from fastapi import APIRouter
from starlette.middleware import Middleware

from app.core.errors import ErrorSpec

MODELS: list[ModuleType] = []
ROUTERS: list[APIRouter] = []
MIDDLEWARES: list[Middleware] = []
ERRORS: list[ErrorSpec] = []
