from __future__ import annotations

import inspect
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from typeyao.base._typing import register_type
from typeyao.base.exceptions import (
    DuplicateUniqueFieldValueError,
    InvalidFieldError,
    InvalidModelError,
    ModelNotFoundError,
    NoPrimaryKeyError,
)
from typeyao.fields import MISSING, FieldInfo

if TYPE_CHECKING:
    from typeyao.model import Model


PROTECTED_MODEL_ATTRIBUTE_NAMES = {
    "__fields_map__",
    "__cache__",
}


class ModelFieldMap(dict[str, FieldInfo]):
    def __init__(self):
        self.pk: FieldInfo | None = None
        self._owner: type[Model] | None = None

    @classmethod
    def from_namespace(cls, namespace: dict[str, Any]) -> ModelFieldMap:
        annotations = namespace.get("__annotations__", {})
        fields_map = cls()
        for name, annotation in annotations.items():
            if name not in namespace and not name.startswith("_"):
                fields_map[name] = FieldInfo(name=name, type=annotation)

        field_names = [
            name
            for name, value in namespace.items()
            # skip private attributes
            if not (name.startswith("_") and not isinstance(value, FieldInfo))
            # skip classmethods and functions
            and not (
                inspect.isfunction(value)
                or inspect.ismethod(value)
                or isinstance(value, classmethod)
            )
            # skip properties
            and not isinstance(value, property)
        ]

        for name in field_names:
            value = namespace.pop(name)
            if not isinstance(value, FieldInfo):
                value = FieldInfo(
                    name=name,
                    default=value,
                    type=annotations.get(name, MISSING),
                )
            fields_map[name] = value
        return fields_map

    def __setitem__(self, key: str, value: Any) -> None:
        if not isinstance(value, FieldInfo):
            raise TypeError(
                f"{self.__class__.__name__} item must be a FieldInfo class. Got {value!r}"
            )
        if not isinstance(key, str):
            raise TypeError(f"{self.__class__.__name__} keys must be strings.")
        if value.primary_key:
            if self.pk:
                raise InvalidModelError(
                    f"Cannot have multiple primary keys: {self.pk.name!r} and {key!r}"
                )
            self.pk = value
        super().__setitem__(key, value)

    def __getitem__(self, __key: str) -> FieldInfo:
        return super().__getitem__(__key)

    def __set_name__(self, owner: type[Model], name: str) -> None:
        self._owner = owner


class ModelMeta(type):
    __fields_map__: ModelFieldMap

    def __new__(
        mcs,
        class_name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        abstract: bool = False,
        **kwargs: Any,
    ) -> type["Model"]:
        mcs._check_for_protected_names(class_name, bases, namespace)
        namespace = mcs._namespace_constructor(namespace, bases)
        namespace["_is_abstract"] = abstract
        cls: type["Model"] = super().__new__(mcs, class_name, bases, namespace)  # type: ignore  # noqa: E501
        cls.__cache__ = ModelCache(cls)
        register_type(cls)
        return cls

    @staticmethod
    def _check_for_protected_names(
        class_name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> None:
        errors = {
            name: f"{name!r} is a protected class attribute name."
            for name in PROTECTED_MODEL_ATTRIBUTE_NAMES.intersection(namespace)
        }
        if len(bases) > 0 and class_name == "Model":
            errors[
                class_name
            ] = "'Model' is a protected class name. Use something else."
        if errors:
            raise InvalidModelError(json.dumps(errors, indent=4))

    @classmethod
    def _namespace_constructor(
        mcs, namespace: dict[str, Any], bases: tuple[type, ...]
    ) -> dict[str, Any]:
        fields_map = ModelFieldMap.from_namespace(namespace)
        class_fields_map = {}
        for base in bases:
            if isinstance(base, ModelMeta):
                for name, field in base.__fields_map__.items():  # type: ignore
                    if name not in fields_map:
                        if field.classfield:  # type: ignore
                            class_fields_map[name] = field  # type: ignore
                        else:
                            fields_map[name] = field.copy()  # type: ignore
                            namespace["__annotations__"][name] = field.type  # type: ignore # noqa: E501
        namespace.update(
            {**fields_map, "__fields_map__": {**fields_map, **class_fields_map}}
        )
        return namespace

    @property
    def pk(cls) -> FieldInfo | None:
        return cls.__fields_map__.pk

    @property
    def field_names(cls) -> set[str]:
        return set(cls.__fields_map__.keys())

    @property
    def fields(cls) -> set[FieldInfo]:
        return set(cls.__fields_map__.values())


class ModelCache:
    model: type["Model"]
    all: set["Model"]

    def __init__(self, model: type["Model"]):
        self.model = model
        self._unique_field_cache = UniqueFieldCache(model)
        self._index_field_cache = IndexFieldCache(model)
        self.all = set()

    def add_model(self, obj: "Model") -> None:
        if not isinstance(obj, self.model):
            raise TypeError(
                f"Can only cache instances of {self.model.__name__}."
            )

        self._unique_field_cache.add_model(obj)
        self._index_field_cache.add_model(obj)
        self.all.add(obj)

    def get(self, pk_value: Any) -> "Model":
        pk = self.model.pk
        if pk is None:
            raise NoPrimaryKeyError(
                f"{self.model.__name__} does not have a primary key."
            )
        value = self._unique_field_cache[pk.name].get(pk_value)
        if not value:
            raise ModelNotFoundError(
                f"{self.model.__name__} with {pk.name}={pk_value} not found."
            )
        return value

    def filter(
        self, error_if_not_found: bool = True, **kwargs: Any
    ) -> set["Model"]:
        invalid_kwargs = set(kwargs.keys()) - set(
            self.model.__fields_map__.keys()
        )
        if invalid_kwargs:
            raise InvalidFieldError(
                f"{self.model.__name__} does not have fields named {invalid_kwargs}."
            )

        # Unique fields are the fastest to filter by, so filter by them if possible
        unique_field_kwargs: dict[str, Any] = {}
        for unique_field_name in self._unique_field_cache:
            if unique_field_name in kwargs:
                unique_field_kwargs[unique_field_name] = kwargs.pop(
                    unique_field_name
                )
        # If there are any unique fields in kwargs, use the unique field cache only
        if unique_field_kwargs:
            obj = self._unique_field_cache.filter(
                error_if_not_found, **unique_field_kwargs
            ).pop()
            # ensure found object matches all other kwargs
            for field_name, value in kwargs.items():
                if getattr(obj, field_name) != value:
                    if error_if_not_found:
                        raise ModelNotFoundError(
                            f"{self.model.__name__} with values {kwargs} not found."
                        )
                    return set()
            return {obj}

        # Otherwise, filter first by index fields (if any), then by other fields (if any)
        index_field_kwargs: dict[str, Any] = {}
        for index_field_name in self._index_field_cache:
            if index_field_name in kwargs:
                index_field_kwargs[index_field_name] = kwargs.pop(
                    index_field_name
                )
        if index_field_kwargs:
            objects = self._index_field_cache.filter(
                error_if_not_found, **index_field_kwargs
            )
        else:
            objects = self.all

        for field_name, value in kwargs.items():
            objects = {
                obj for obj in objects if getattr(obj, field_name) == value
            }
            if not objects:
                if error_if_not_found:
                    raise ModelNotFoundError(
                        f"{self.model.__name__} with values {kwargs} not found."
                    )
                break
        return objects


class UniqueFieldCache(dict[str, dict[Any, "Model"]]):
    def __init__(self, model: type["Model"]):
        self.model = model
        self.update({f.name: {} for f in model.fields if f.unique})

    def add_model(self, obj: "Model") -> None:
        if not isinstance(obj, self.model):
            raise TypeError(
                f"Can only cache instances of {self.model.__name__}."
            )
        errors = {}
        for field_name, cache in self.items():
            value = getattr(obj, field_name)
            existing = cache.get(value)
            if existing is not None:
                errors[
                    field_name
                ] = f"The value of {field_name}={value} already exists in {existing}."
        if errors:
            raise DuplicateUniqueFieldValueError(errors)

        for field_name, cache in self.items():
            cache[getattr(obj, field_name)] = obj

    def filter(
        self, error_if_not_found: bool = True, **kwargs: Any
    ) -> set["Model"]:
        invalid_kwargs = set(kwargs.keys()) - set(self.model.field_names)
        if invalid_kwargs:
            raise InvalidFieldError(
                f"{self.model.__name__} does not have fields named {invalid_kwargs}."
            )

        filters = list(kwargs.items())
        filter_field_name, filter_value = filters.pop()
        model = self[filter_field_name].get(filter_value)
        if not model:
            if error_if_not_found:
                raise ModelNotFoundError(
                    f"{self.model.__name__} with values {kwargs} not found."
                )
            return set()
        for filter_field_name, filter_value in filters:
            if getattr(model, filter_field_name) != filter_value:
                if error_if_not_found:
                    raise ModelNotFoundError(
                        f"{self.model.__name__} with values {kwargs} not found."
                    )
                return set()
        return {model}


class IndexFieldCache(dict[str, dict[str, list["Model"]]]):
    def __init__(self, model: type["Model"]):
        self.model = model
        self.update(
            {
                f.name: defaultdict(list["Model"])
                for f in model.fields
                if f.index
            }
        )

    def add_model(self, obj: "Model") -> None:
        if not isinstance(obj, self.model):
            raise TypeError(
                f"Can only cache instances of {self.model.__name__}."
            )
        for field_name, cache in self.items():
            cache[getattr(obj, field_name)].append(obj)

    def filter(
        self, error_if_not_found: bool = True, **kwargs: Any
    ) -> set["Model"]:
        invalid_kwargs = set(kwargs.keys()) - set(self.model.field_names)
        if invalid_kwargs:
            raise InvalidFieldError(
                f"{self.model.__name__} does not have fields named {invalid_kwargs}."
            )

        kwargs_items = list(kwargs.items())
        filter_field_name, filter_value = kwargs_items.pop()
        models = self[filter_field_name].get(filter_value, [])
        while kwargs_items:
            filter_field_name, filter_value = kwargs_items.pop()
            models = [
                m
                for m in models
                if getattr(m, filter_field_name) == filter_value
            ]
            if not models:
                if error_if_not_found:
                    raise ModelNotFoundError(
                        f"{self.model.__name__} with values {kwargs} not found."
                    )
        return set(models)
