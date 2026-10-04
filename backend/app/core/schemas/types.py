from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer

from app.core.schemas.validators import PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH

Username = Annotated[str, Field(max_length=USERNAME_MAX_LENGTH)]
Password = Annotated[str, Field(max_length=PASSWORD_MAX_LENGTH)]
SearchText = Annotated[str, Field(max_length=100)]
OptionalSearchText = SearchText | None

PlainDecimal = Annotated[
    Decimal, PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json")
]
