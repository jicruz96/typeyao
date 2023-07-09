from __future__ import annotations

import json
from typing import Any

from typeyao.base._meta import (
    PROTECTED_MODEL_ATTRIBUTE_NAMES,
    ModelCache,
    ModelMeta,
)
from typeyao.base._typing import MISSING, InvalidTypeError
from typeyao.base.exceptions import InvalidModelError
from typeyao.fields import FieldInfo


class Model(metaclass=ModelMeta):
    __fields_map__: dict[str, FieldInfo]
    __cache__: ModelCache
    _is_abstract: bool

    def __init__(self, **kwargs: Any):
        if self._is_abstract:
            raise InvalidModelError(
                f"Cannot instantiate abstract model: {self.__class__.__name__}"
            )
        self.__init_kwargs__(kwargs)
        self.__init_defaults__(exclude=set(kwargs))
        self.__post_init__()
        self.__cache__.add_model(self)  # type: ignore

    def __init_kwargs__(self, init_kwargs: dict[str, Any]) -> None:
        errors = {}
        for kw, value in init_kwargs.items():
            field = self.__fields_map__.get(kw)
            try:
                assert (
                    field is not None
                ), f"{kw} is not a field in {self.__class__.__name__}."
                assert (
                    field.classfield is False
                ), f"'{field.name}' is a class variable. It can't be overwritten."
                assert (
                    field.init is True
                ), f"'{field.name}' field has init=False"
                setattr(self, field.name, value)
            except (AssertionError, InvalidTypeError) as e:
                errors[kw] = str(e)

        if errors:
            raise InvalidModelError("\n" + json.dumps(errors, indent=4))

    def __init_defaults__(
        self, exclude: set[str] | None = None
    ) -> set[FieldInfo]:
        exclude = exclude or set()
        fields = {
            f
            for f in self.__fields_map__.values()
            if f.name not in exclude and not f.classfield
        }
        fields_with_setters = {
            f for f in fields if hasattr(self, f"set_{f.name}")
        }
        fields_with_default_factories = {
            f for f in fields if f.default_factory is not MISSING
        }
        fields_with_defaults = {f for f in fields if f.default is not MISSING}
        missing_fields = (
            fields
            - fields_with_setters
            - fields_with_default_factories
            - fields_with_defaults
        )
        if missing_fields:
            raise InvalidModelError(
                f"Missing fields: {', '.join(map(lambda f: repr(f.name), missing_fields))}"
            )
        for field in fields_with_defaults:
            setattr(self, field.name, field.default)

        for field in fields_with_default_factories:
            setattr(self, field.name, field.default_factory())  # type: ignore

        for field in fields_with_setters:
            setattr(self, field.name, getattr(self, f"set_{field.name}")())
        return fields

    def __post_init__(self) -> None:
        pass

    def __setattr__(self, __name: str, __value: Any) -> None:
        if __name in PROTECTED_MODEL_ATTRIBUTE_NAMES:
            raise AttributeError(
                f"{__name!r} is a protected attribute of {self.__class__.__name__}"
            )
        return super().__setattr__(__name, __value)

    @classmethod
    def update_forward_refs(cls) -> None:
        """Update forward references on all fields"""
        for field in cls.__fields_map__.values():
            field.update_forward_refs()

    def dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__fields_map__.keys()
        }

    @classmethod
    def all(cls) -> set[Model]:
        return cls.__cache__.all

    @classmethod
    def filter(cls, **kwargs: Any) -> set[Model]:
        return cls.__cache__.filter(**kwargs)

    @classmethod
    def get(cls, pk: Any) -> Model:
        return cls.__cache__.get(pk)
