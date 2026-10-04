from pydantic import BaseModel


class Message(BaseModel):
    """Respuesta de las acciones que no devuelven un recurso."""

    detail: str
