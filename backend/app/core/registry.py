from aerich import models as aerich_models
from fastapi_idempotency.stores import tortoise as idempotency_models

from app.core.models import event, login_attempt, role, session, user
from app.core.routes import auth, events, roles, system, users

MODELS = [aerich_models, idempotency_models, event, login_attempt, role, session, user]
ROUTERS = [auth.router, events.router, roles.router, system.router, users.router]
