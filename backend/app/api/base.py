"""Request-model base for every API endpoint: NaN and ±Infinity are rejected with a 422 at the
boundary, so they can never reach a calculation (where they would give a 500 or a blank result)."""

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict


class BaseModel(_PydanticBaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
