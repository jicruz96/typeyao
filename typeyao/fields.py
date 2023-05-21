from __future__ import annotations

import inspect
import operator
import typing
from collections.abc import Callable, Mapping
from functools import reduce

from typeyao.base._typing import (
    MISSING,
    InvalidTypeError,
    MissingType,
    check_type,
    get_type_from_string,
    is_classvar,
    type_registry,
)

if typing.TYPE_CHECKING:
    from typeyao.model import Model


class InvalidFieldError(Exception):
    pass


def Field(
    name: typing.Optional[str] = None,
    default: typing.Any = MISSING,
    default_factory: Callable[[], typing.Any] | MissingType = MISSING,
    type: typing.Any = MISSING,
    init: bool = True,
    primary_key: bool = False,
    unique: bool = False,
    index: bool = False,
    classfield: bool = False,
    choices: typing.Optional[list[typing.Any]] = None,
    repr: bool = True,
    hash: bool = True,
    compare: bool = True,
    metadata: typing.Optional[Mapping[typing.Any, typing.Any]] = None,
) -> typing.Any:
    return FieldInfo(
        name=name,
        default=default,
        default_factory=default_factory,
        type=type,
        init=init,
        primary_key=primary_key,
        unique=unique,
        index=index,
        classfield=classfield,
        choices=choices,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata=metadata,
    )


class FieldInfo:
    """Represents a field in a typeyao model.

    Attributes:
        primary_key: if True, this field is the primary key for the model. This field must be unique across all
            instances of the model.
        default: default field value.
        default_factory: 0-argument function called to initialize a field's value.
        init: if True, the field will be a parameter to the class's __init__() function. If False, it is up to the
            caller to set a default, default_factory, or include a field initializer in the class, via
            __post_init__() or an instance method named "set_{field_name}()".
        unique: if True, the field must be unique across all instances of the model. Cannot be False if primary_key is
            True.
        index: if True, the field will be a table index for the model.
        classfield: if True, the field is a class variable (i.e. shared by all instances of the model)
        choices: If provided, allowed values for the field.
        repr: if True, the field will be included in the object's repr().
        compare: if True, the field will be used in comparison functions.
        metadata: if specified, must be a mapping which is stored but not otherwise examined by dataclass.

    Raises:
        InvalidFieldError: if default and default_factory are both set
        InvalidFieldError: if default is set, and unique or primary_key set to True.
    """

    def __init__(
        self,
        *,
        name: typing.Optional[str] = None,
        default: typing.Any = MISSING,
        default_factory: Callable[[], typing.Any] | MissingType = MISSING,
        type: typing.Any = MISSING,
        const: bool = False,
        init: bool = True,
        primary_key: bool = False,
        unique: bool = False,
        index: bool = False,
        classfield: bool = False,
        choices: typing.Optional[list[typing.Any]] = None,
        repr: bool = True,
        hash: bool = True,
        compare: bool = True,
        metadata: typing.Optional[Mapping[typing.Any, typing.Any]] = None,
    ) -> None:
        self.__name = name
        self.__default = default
        self.__default_factory = default_factory
        self.__const = const
        self.__init = init
        self.__repr = repr
        self.__hash = hash
        self.__compare = compare
        self.__metadata = metadata
        self.__primary_key = primary_key
        self.__unique = (primary_key is True) or unique
        self.__index = index
        self.__classfield = classfield
        self.__choices = choices or []
        self.__type = type if type is not None else None.__class__
        self.__owner: type["Model"] | None = None
        if default is not MISSING:
            for attr_name in ("default_factory", "unique", "primary_key"):
                if getattr(self, attr_name) not in (MISSING, False):
                    raise InvalidFieldError(f"Cannot specify both default and {attr_name}")

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.__name} "
            f"type={self.type} default={self.default} default_factory={self.default_factory} "
            f"init={self.init} repr={self.repr} hash={self.hash} compare={self.compare} metadata={self.metadata} "
            f"classfield={self.classfield} unique={self.unique} index={self.index} choices={self.choices}>"
        )

    @property
    def owner(self) -> type["Model"] | None:
        return self.__owner

    @property
    def name(self) -> str:
        return self.__name or "Unnamed"

    @property
    def primary_key(self) -> bool:
        return self.__primary_key

    @property
    def type(self) -> type | MissingType:
        return self.__type

    @property
    def default(self) -> typing.Any:
        return self.__default

    @property
    def default_factory(self) -> Callable[[], typing.Any] | MissingType:
        return self.__default_factory

    @property
    def const(self) -> bool:
        return self.__const

    @property
    def init(self) -> bool:
        return self.__init

    @property
    def repr(self) -> bool:
        return self.__repr

    @property
    def hash(self) -> bool:
        return self.__hash

    @property
    def compare(self) -> bool:
        return self.__compare

    @property
    def metadata(self) -> Mapping[typing.Any, typing.Any] | None:
        return self.__metadata

    @property
    def classfield(self) -> bool:
        return self.__classfield

    @property
    def unique(self) -> bool:
        return self.__unique is True or self.primary_key is True

    @property
    def index(self) -> bool:
        return self.__index is True

    @property
    def choices(self) -> list[typing.Any]:
        # return a copy to prevent modification
        return self.__choices.copy()

    def update_forward_refs(self) -> None:
        """Update forward references on the field's type."""
        if isinstance(self.type, str):
            type_ = get_type_from_string(self.type)
            if is_classvar(type_):
                if self.classfield is False:
                    raise InvalidFieldError(
                        f"Corrupted field {self.name!r} has a classvar type ({type_}) but classfield is False: {self}"
                    )
                self.__type = typing.Union[reduce(operator.or_, type_.__args__)]  # type: ignore
            else:
                self.__type = type_
        elif isinstance(self.type, typing.ForwardRef):
            self.__type = type_registry[self.type.__forward_arg__]

    def __get__(self, instance: "Model" | None, owner: type["Model"]) -> typing.Any:
        if self.classfield:
            return self.default
        if instance is None:
            return self
        return instance.__dict__[self.name]  # type: ignore

    def _validate_value_type(self, value: typing.Any) -> None:
        assert not isinstance(self.type, MissingType), f"type unset for {self}"
        try:
            check_type(value=value, type_=self.type)
        except InvalidTypeError:
            raise InvalidTypeError(
                f"Invalid type for field {self.name!r}: expected {self.type.__name__}. "
                f"got {value.__class__.__name__}."
            ) from None
        if self.choices and value not in self.choices:
            raise InvalidTypeError(f"Value must be one of {','.join(map(repr,self.choices))} but value was {value}")

    def __set_classvar__(self, owner: type["Model"], value: typing.Any) -> None:
        if owner is not self.owner:
            raise InvalidFieldError(f"Field {self.name!r} on {owner.__name__} is not a classfield.")
        self._validate_value_type(value)
        self.__default = value

    def __set__(self, instance: "Model", value: typing.Any) -> None:
        self._validate_value_type(value)
        instance.__dict__[self.name] = value  # type: ignore

    def __set_name__(self, owner: type["Model"], name: str) -> None:
        if self.owner:
            raise InvalidFieldError(f"Field {name!r} on {owner.__name__} has already been set to {self.owner}")

        if self.__name is not None and self.__name != name:
            raise InvalidFieldError(f"Field '{name}' has conflicting names: {self.__name} != {name}")

        annotation = owner.__annotations__.get(name, MISSING)
        if self.type is MISSING:
            if annotation is MISSING:
                raise InvalidFieldError(
                    f"Field {name!r} on {owner.__name__} must specify a type or have a type annotation."
                )
            self.__type = annotation
        elif annotation is not MISSING and self.type != annotation:
            raise InvalidFieldError(f"Field '{name}' has conflicting type annotations: {self.type} != {annotation}")

        if is_classvar(self.type) or (isinstance(self.type, str) and "ClassVar" in self.type) or self.classfield:
            self._validate_classvar_default_field(owner, name)
            self.__classfield = True
            self.__init = False
            self.__repr = False
            self.__hash = False
            self.__compare = False

            if is_classvar(self.type):
                self.__type = typing.Union[reduce(operator.or_, self.type.__args__)]  # type: ignore

            setter_name = f"set_{name}"
            if hasattr(owner, setter_name):
                try:
                    self.__default = getattr(owner, setter_name)()
                except Exception as e:
                    raise InvalidFieldError(
                        f"Error while setting class variable '{name}' via {setter_name}: {e.__class__.__name__}: "
                        f"{e}"
                    )
            elif not isinstance(self.default_factory, MissingType):
                try:
                    self.__default = self.default_factory()
                except Exception as e:
                    raise InvalidFieldError(
                        f"Error while setting class variable '{name}' via default factory: {e.__class__.__name__}: "
                        f"{e}"
                    )
        else:
            self._validate_instance_field_defaults(owner, name)
        self.__name = name
        self.__owner = owner

    def copy(self) -> FieldInfo:
        """Return a copy of the field, without the owner and name set."""
        return self.__class__(
            type=self.type,
            default=self.default,
            default_factory=self.default_factory,
            const=self.const,
            init=self.init,
            repr=self.repr,
            hash=self.hash,
            compare=self.compare,
            metadata=self.metadata,
            unique=self.unique,
            index=self.index,
            choices=self.choices,
            primary_key=self.primary_key,
            classfield=self.classfield,
        )

    def _validate_classvar_default_field(self, owner: type["Model"], name: str):
        if self.primary_key is True:
            raise InvalidFieldError(f"Field '{name}' cannot be a primary key and a class field.")
        if self.unique is True:
            raise InvalidFieldError(f"Field '{name}' cannot be unique and a class field.")
        if self.index is True:
            raise InvalidFieldError(f"Field '{name}' cannot be indexed and a class field.")
        if self.choices:
            raise InvalidFieldError(f"Field '{name}' cannot have choices and be a class field.")
        setter_name = f"set_{name}"
        setter_repr = f"{owner.__name__}.{setter_name}()"  # type: ignore
        setter = getattr(owner, setter_name, MISSING)
        if setter != MISSING and not (inspect.ismethod(setter) and setter.__self__ is owner):
            raise InvalidFieldError(
                f"'{name}' field is a class attribute, but its setter (i.e {setter_repr}) is not a classmethod"
            )
        self._validate_instance_field_defaults(owner, name)

    def _validate_instance_field_defaults(self, owner: type["Model"], name: str):
        setter_name = f"set_{name}"
        setter_repr = f"{owner.__name__}.{setter_name}()"
        defaults = {getattr(owner, f"set_{name}", MISSING), self.default, self.default_factory} - {MISSING}
        default_count = len(defaults)
        if default_count > 1:
            raise InvalidFieldError(
                f"Field '{name}' must have only one of 'default', 'default_factory', and {setter_repr!r}"
            )

        if self.init is False and default_count == 0:
            raise InvalidFieldError(f"Field '{name}' must have a 'default', 'default_factory' or {setter_repr!r}")
