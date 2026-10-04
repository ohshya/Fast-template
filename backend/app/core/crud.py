import inspect
from datetime import date, datetime
from decimal import Decimal
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi_pagination import Page
from fastapi_pagination.ext.tortoise import apaginate
from pydantic import AwareDatetime, BaseModel
from tortoise.expressions import Q
from tortoise.fields.relational import ForeignKeyFieldInstance
from tortoise.queryset import QuerySet

from app.core.dependencies import requires
from app.core.errors import AppError, Err, ErrorSpec
from app.core.models.entity import Entity
from app.core.models.user import Users
from app.core.permissions import CrudPermissions
from app.core.schemas.common import Message
from app.core.schemas.types import SearchText


class Resource[M: Entity]:
    """CRUD declarativo: `mount()` añade los siete endpoints. Se personaliza con los hooks."""

    model: type[M]
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    out_schema: type[BaseModel]
    permissions: CrudPermissions
    not_found: ErrorSpec = Err.NOT_FOUND
    search_fields: tuple[str, ...] = ()
    filter_fields: tuple[str, ...] = ()
    text_fields: tuple[str, ...] = ()
    range_fields: tuple[str, ...] = ()
    sort_fields: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ("-id",)

    async def before_create(self, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        """Ajusta los datos antes de crear."""
        return data

    async def before_update(self, item: M, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        """Ajusta los cambios antes de aplicarlos."""
        return data

    async def after_create(self, item: M, actor: Users) -> None:
        """Efectos tras crear, dentro de la misma transacción."""

    async def after_update(self, item: M, changes: dict[str, Any], actor: Users) -> None:
        """Efectos tras aplicar los cambios (`changes`), dentro de la misma transacción."""

    async def before_delete(self, item: M, actor: Users, *, hard: bool) -> None:
        """Valida antes de eliminar. `hard`: borrado definitivo."""

    async def after_delete(self, item: M, actor: Users) -> None:
        """Efectos tras una eliminación reversible."""

    async def before_restore(self, item: M, actor: Users) -> None:
        """Valida antes de restaurar."""

    async def after_restore(self, item: M, actor: Users) -> None:
        """Efectos tras restaurar."""

    async def serialize(self, items: list[M]) -> list[Any]:
        """Registros a respuestas. Se sobrescribe para campos calculados."""
        return [self.out_schema.model_validate(item, from_attributes=True) for item in items]

    async def get(self, item_id: UUID, *, include_deleted: bool = False) -> M:
        """Registro por id, o el error `not_found`."""
        query = self.model.with_deleted() if include_deleted else self.model.all()
        item = await query.filter(id=item_id).first()
        if item is None:
            raise AppError(self.not_found, details={"id": str(item_id)})
        return item

    def check_required(self, data: dict[str, Any]) -> None:
        """Falla si un campo obligatorio llega vacío."""
        vacios = {
            name: "No puede quedar vacío"
            for name, value in data.items()
            if value is None
            and (field := self.model._meta.fields_map.get(name)) is not None
            and not field.null
        }
        if vacios:
            raise AppError(Err.VALIDATION, fields=vacios)

    async def check_unique(self, data: dict[str, Any], exclude_id: UUID | None = None) -> None:
        """Falla si un campo único ya existe, incluso en eliminados."""
        taken: dict[str, str] = {}
        for name, value in data.items():
            field = self.model._meta.fields_map.get(name)
            if field is None or field.pk or not field.unique:
                continue
            query = self.model.with_deleted().filter(**{name: value})
            if exclude_id is not None:
                query = query.exclude(id=exclude_id)
            clash = await query.first()
            if clash is not None:
                taken[name] = (
                    "Ya existe un registro eliminado con este valor: restáuralo o usa otro"
                    if clash.is_deleted
                    else "Ya existe un registro con este valor"
                )
        if taken:
            raise AppError(Err.DUPLICATED, fields=taken)

    async def check_relations(self, data: dict[str, Any]) -> None:
        """Falla si una clave foránea apunta a un registro inexistente o eliminado."""
        missing: dict[str, str] = {}
        for name in self.model._meta.fk_fields:
            field: Any = self.model._meta.fields_map[name]
            value = data.get(field.source_field)
            if value is not None and not await field.related_model.filter(pk=value).exists():
                missing[field.source_field] = "El registro relacionado no existe"
        if missing:
            raise AppError(Err.RELATED_NOT_FOUND, fields=missing)

    def relations_of(self, item: M) -> dict[str, Any]:
        """Claves foráneas de un registro."""
        values: dict[str, Any] = {}
        for name in self.model._meta.fk_fields:
            source = self.model._meta.fields_map[name].source_field
            if source:
                values[source] = getattr(item, source)
        return values

    def _column_type(self, attribute: str, name: str) -> Any:
        """Tipo de una columna declarada en un atributo del recurso, o error de configuración."""
        columns = set(self.model._meta.fields_map) | {
            f"{key}_id"
            for key, value in self.model._meta.fields_map.items()
            if isinstance(value, ForeignKeyFieldInstance)
        }
        field = self.out_schema.model_fields.get(name)
        if field is None or name not in columns:
            raise RuntimeError(
                f"{type(self).__name__}.{attribute}: '{name}' debe ser una columna de "
                f"{self.model.__name__} y un campo de {self.out_schema.__name__}"
            )
        annotation: Any = field.annotation
        if get_origin(annotation) in (Union, UnionType):
            annotation = next(arg for arg in get_args(annotation) if arg is not type(None))
        return annotation

    def filters_class(self) -> type:
        """Dependencia del listado: un parámetro de query por filtro (así los documenta OpenAPI)."""
        params: list[tuple[str, Any, Any]] = [
            ("search", Annotated[str | None, Query(max_length=100)], None),
            ("deleted", bool, False),
            ("sort", Annotated[str | None, Query(max_length=200)], None),
        ]
        for name in self.filter_fields:
            annotation = self._column_type("filter_fields", name)
            kind = SearchText if annotation is str else annotation
            params.append((name, Annotated[list[kind] | None, Query()], None))
        for name in self.text_fields:
            self._column_type("text_fields", name)
            params.append((f"{name}_contains", Annotated[str | None, Query(max_length=100)], None))
        for name in self.range_fields:
            annotation = self._column_type("range_fields", name)
            if annotation is datetime:
                annotation = AwareDatetime
            elif annotation not in (int, float, Decimal, date):
                raise RuntimeError(
                    f"{type(self).__name__}.range_fields: '{name}' no es un número ni una fecha"
                )
            params.append((f"{name}_from", annotation | None, None))
            params.append((f"{name}_to", annotation | None, None))
        for name in self.sort_fields:
            self._column_type("sort_fields", name)
        parameters = [
            inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation
            )
            for name, annotation, default in params
        ]

        class Filters:
            """Valores recibidos de los parámetros de query del listado."""

            __signature__ = inspect.Signature(parameters)

            def __init__(self, **values: Any) -> None:
                self.__dict__.update(values)

        return Filters

    def order_of(self, sort: str | None) -> tuple[str, ...]:
        """Orden de `?sort=` (columnas permitidas, `-` descendente) o el de `ordering`."""
        columns = [part.strip() for part in (sort or "").split(",") if part.strip()]
        if not columns:
            return self.ordering
        if len(columns) > 4 or any(
            column.lstrip("-") not in self.sort_fields for column in columns
        ):
            allowed = ", ".join(self.sort_fields) or "ninguna"
            raise AppError(
                Err.VALIDATION, fields={"sort": f"Columnas permitidas (máximo 4): {allowed}"}
            )
        return (*columns, "id")

    def list_query(self, filters: Any) -> QuerySet[M]:
        """Consulta del listado."""
        if filters.deleted:
            query = self.model.with_deleted().exclude(deleted_at=None)
        else:
            query = self.model.all()
        if filters.search and self.search_fields:
            condiciones = [
                Q(**{f"{name}__icontains": filters.search}) for name in self.search_fields
            ]
            query = query.filter(Q(*condiciones, join_type="OR"))
        for name in self.filter_fields:
            values = getattr(filters, name)
            if values:
                query = query.filter(**{f"{name}__in": values})
        for name in self.text_fields:
            text = getattr(filters, f"{name}_contains")
            if text:
                query = query.filter(**{f"{name}__icontains": text})
        for name in self.range_fields:
            low, high = getattr(filters, f"{name}_from"), getattr(filters, f"{name}_to")
            if low is not None and high is not None and low > high:
                raise AppError(
                    Err.VALIDATION, fields={f"{name}_to": "Debe ser igual o posterior al inicio"}
                )
            if low is not None:
                query = query.filter(**{f"{name}__gte": low})
            if high is not None:
                query = query.filter(**{f"{name}__lte": high})
        return query.order_by(*self.order_of(filters.sort))

    async def one(self, item: M) -> Any:
        """Respuesta de un registro."""
        return (await self.serialize([item]))[0]

    def mount(self, router: APIRouter) -> APIRouter:
        """Añade los siete endpoints. Llamar después de las rutas propias."""
        perms = self.permissions
        filters_class = self.filters_class()

        async def transform(items: Any) -> Any:
            return await self.serialize(list(items))

        async def list_items(
            filters: Any = Depends(filters_class), actor: Users = requires(perms.list)
        ) -> Any:
            return await apaginate(self.list_query(filters), transformer=transform)

        async def read_item(item_id: UUID, actor: Users = requires(perms.read)) -> Any:
            return await self.one(await self.get(item_id, include_deleted=True))

        async def create_item(data: Any, actor: Users = requires(perms.create)) -> Any:
            values = data.model_dump()
            self.check_required(values)
            values = await self.before_create(values, actor)
            await self.check_unique(values)
            await self.check_relations(values)
            item = await self.model.create(**values)
            await self.after_create(item, actor)
            return await self.one(item)

        async def update_item(
            item_id: UUID, data: Any, actor: Users = requires(perms.update)
        ) -> Any:
            item = await self.get(item_id)
            changes = data.model_dump(exclude_unset=True)
            self.check_required(changes)
            changes = await self.before_update(item, changes, actor)
            await self.check_unique(changes, exclude_id=item_id)
            await self.check_relations(changes)
            for field, value in changes.items():
                setattr(item, field, value)
            if changes:
                await item.save(update_fields=list(changes))
                await self.after_update(item, changes, actor)
            return await self.one(item)

        async def delete_item(item_id: UUID, actor: Users = requires(perms.delete)) -> Message:
            item = await self.get(item_id)
            await self.before_delete(item, actor, hard=False)
            await item.soft_delete()
            await self.after_delete(item, actor)
            return Message(detail=f"{item.audit_label() or item_id} eliminado")

        async def restore_item(item_id: UUID, actor: Users = requires(perms.restore)) -> Any:
            item = await self.get(item_id, include_deleted=True)
            if not item.is_deleted:
                raise AppError(Err.RESTORE_NOT_DELETED, details={"id": str(item_id)})
            await self.before_restore(item, actor)
            await self.check_relations(self.relations_of(item))
            await item.restore()
            await self.after_restore(item, actor)
            return await self.one(item)

        async def hard_delete_item(
            item_id: UUID, actor: Users = requires(perms.hard_delete)
        ) -> Message:
            item = await self.get(item_id, include_deleted=True)
            await self.before_delete(item, actor, hard=True)
            etiqueta = item.audit_label() or str(item_id)
            await item.hard_delete()
            return Message(detail=f"{etiqueta} borrado definitivamente")

        create_item.__annotations__ = {**create_item.__annotations__, "data": self.create_schema}
        update_item.__annotations__ = {**update_item.__annotations__, "data": self.update_schema}

        out = self.out_schema
        router.add_api_route(
            "/", list_items, methods=["GET"], response_model=Page[out], name=perms.list.key
        )
        router.add_api_route(
            "/",
            create_item,
            methods=["POST"],
            response_model=out,
            status_code=201,
            name=perms.create.key,
        )
        router.add_api_route(
            "/{item_id}", read_item, methods=["GET"], response_model=out, name=perms.read.key
        )
        router.add_api_route(
            "/{item_id}",
            update_item,
            methods=["PATCH"],
            response_model=out,
            name=perms.update.key,
        )
        router.add_api_route(
            "/{item_id}",
            delete_item,
            methods=["DELETE"],
            response_model=Message,
            name=perms.delete.key,
        )
        router.add_api_route(
            "/{item_id}/restore",
            restore_item,
            methods=["POST"],
            response_model=out,
            name=perms.restore.key,
        )
        router.add_api_route(
            "/{item_id}/hard",
            hard_delete_item,
            methods=["DELETE"],
            response_model=Message,
            name=perms.hard_delete.key,
        )
        return router
