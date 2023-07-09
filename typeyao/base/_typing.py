# isort:skip_file
from __future__ import annotations

import types
from datetime import date, datetime
from functools import partial
from typing import *  # noqa: F403, F401  # type: ignore
from typing import GenericAlias  # type: ignore
from typing import _GenericAlias  # type: ignore
from typing import _SpecialGenericAlias  # type: ignore
from typing import _UnionGenericAlias  # type: ignore
from typing import Any, Callable, ClassVar, ForwardRef, Optional, Type
from collections.abc import Collection


class InvalidTypeError(Exception):
    pass


class TypeNameAlreadyRegisteredError(Exception):
    pass


class MissingType:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = MissingType()


class TypeRegistry(dict[str, type]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for arg in args:
            self.register(type_=arg)
        for key, value in kwargs.items():
            self.register(type_=value, name=key)

    def register(self, type_: type | None = None, *, name: Optional[str] = None) -> type | Callable[[type], type]:
        def wrap(type_: type, name: Optional[str] = None) -> type:
            name = name if name is not None else type_.__name__
            if name in self.keys():
                if self[name] is type_:
                    return type_
                raise TypeNameAlreadyRegisteredError(f"Cannot overwrite registered type: '{name}': {self[name]}")
            self[name] = type_
            return type_

        if type_ is None:
            return partial(wrap, name=name)
        return wrap(type_=type_, name=name)

    def __contains__(self, __key: object) -> bool:
        if isinstance(__key, str):
            return super().__contains__(__key)
        return __key in self.values()

    def __getitem__(self, __key: str) -> type:
        return super().__getitem__(__key)


type_registry = TypeRegistry(
    date, datetime, bool, int, list, None.__class__, set, dict, tuple, str, float, bytes, Collection
)

register_type = type_registry.register


def is_optional_type(type_: Any) -> bool:
    return isinstance(type_, _UnionGenericAlias) and type_._name == "Optional"


def is_union_type(type_: Any) -> bool:
    return isinstance(type_, types.UnionType) or isinstance(type_, _UnionGenericAlias)


def is_classvar(type_: Any) -> bool:
    return type_ is ClassVar or (is_nested_generic_alias(type_) and type_.__origin__ is ClassVar)


def is_simple_generic_alias(type_: Any) -> bool:
    return isinstance(type_, _SpecialGenericAlias)


def is_nested_generic_alias(type_: Any) -> bool:
    return (
        isinstance(type_, (GenericAlias, _GenericAlias)) and hasattr(type_, "__origin__") and hasattr(type_, "__args__")
    )


def is_Type(type_: Any) -> bool:
    return is_nested_generic_alias(type_) and type_.__name__ == "Type"


def is_forward_ref(type_: Any) -> bool:
    return isinstance(type_, ForwardRef)


def _validate_nested_types(
    value: Any,
    types: tuple[type, ...],
    raise_on_exception: bool = True,
    check_class: bool = False,
) -> bool:
    for type_ in types:
        try:
            if check_type(value, type_, raise_on_exception, check_class) is True:
                return True
        except InvalidTypeError:
            continue
    if raise_on_exception:
        error_message = f"Invalid value {value!r} of type {type(value)} must be "
        if check_class:
            error_message += "a subclass of "
        error_message += f"one of: {', '.join(map(str, types))}"
        raise InvalidTypeError(error_message)
    return False


def is_alias(type_: Any) -> bool:
    return is_simple_generic_alias(type_) or is_nested_generic_alias(type_)


def check_type(
    value: Any,
    type_: Any,
    raise_on_exception: bool = True,
    check_class: bool = False,
) -> bool:
    if isinstance(type_, str):
        type_ = get_type_from_string(type_)

    if is_optional_type(type_) or is_union_type(type_) or is_Type(type_):
        check_class = is_Type(type_)
        return _validate_nested_types(
            value,
            type_.__args__,
            raise_on_exception,
            check_class=check_class,
        )

    if is_classvar(type_):
        raise InvalidTypeError("Cannot validate type of a ClassVar")

    if is_alias(type_):
        assert type_.__origin__ != type, "nah, son"
        type_ = type_.__origin__

    if type_ is None:
        type_name = type_.__class__.__name__
    elif type_ in type_registry:
        type_name = type_.__name__
    elif is_forward_ref(type_):
        if type_.__forward_arg__ not in type_registry:
            raise InvalidTypeError(f"ForwardRef for unknown type '{type_.__forward_arg__}'")
        type_name = type_.__forward_arg__
    else:
        error_message = f"Unknown type {type_}. Got value {value} of type {type(value)}"
        if raise_on_exception:
            raise InvalidTypeError(error_message)
        return False

    registered_type = type_registry[type_name]
    if check_class:
        try:
            result = issubclass(value, registered_type)
        except TypeError:
            result = False
    else:
        result = isinstance(value, registered_type)
    if result is False and raise_on_exception is True:
        expected_type = (registered_type.__class__ if check_class else registered_type).__name__
        raise InvalidTypeError(
            f"value must be of type {expected_type}, not of type {type(value).__name__} (value: {value!r})"
        )
    return result


def get_type_from_string(type_string: str) -> Any:
    _locals = locals()
    _locals.update(type_registry)
    varname = "type_"
    exec(f"{varname} = {type_string}", globals(), _locals)
    return _locals[varname]


if __name__ == "__main__":
    from typing import List, Tuple

    int_or_str = int | str

    class Foo:
        pass

    type_registry.register(Foo)

    test_cases = [
        check_type(None, None),
        check_type(None, Optional[int]),
        check_type(1, int_or_str),
        check_type([], list),
        check_type([], List),
        check_type([], list[int]),
        check_type([], List[int]),
        check_type(tuple(), tuple),
        check_type(tuple(), Tuple),
        check_type(tuple(), Tuple[int | str, ...]),
        check_type(True, bool),
        check_type({}, dict),
        check_type({}, dict[str, str]),
        check_type(1, ForwardRef("int")),
        check_type("not an int", ForwardRef("int"), raise_on_exception=False) is False,
        check_type(Foo, Type[Foo]),
    ]
    assert all(test_cases)
