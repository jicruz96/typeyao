
# `typeyao` - yet another data validation library

### :warning: **You _probably_ shouldn't use this.** :warning:

This was a fun experiment of mine in learning some meta-programming skills for Python. It's also a pain to maintain, so I'm not working on it anymore. Use it at your own risk.

#### **TL;DR**
* `typeyao`
  * ... is a dataclass-flavored library similar to `pydantic` and `dataclasses`.
  * ... can be used as an in-memory database, which is nice for prototyping.
  * ... handles nested data better.
  * ... validates data types better than `dataclasses`, but not as well as `pydantic`.
  * ... doesn't coerce data like `pydantic` does.
  * ... is pronounced "type-yao" (like "type-yow").
* You're probably better off using `pydantic` anyways since it's much better supported by the Python ecosystem, so use `typeyao` at your own risk.

## Requirements
* Python 3.10+

## Install

Clone this repo and use `poetry`  to install the environment.

## Usage

### Use `typeyao` the same way you would use `dataclasses` or `pydantic`:

```python
# inside some .py file...
from typeyao import Model

class Person(Model):
    name: str

Person(name="J.I.")  # ✅ nice
Person(name=1)  # 🙅🏽‍♂️ InvalidModelError
```

`Person(name=1)` will raise a helpful `InvalidModelError` that resembles a JSON Schema validation error:

```json
{
    "name": "The value 1 of type <class 'int'> must be of type <class 'str'>"
}
```

### In-memory database

If you want to prototype a web application quickly and don't want to deal with the overhead of setting up a database, you can use `typeyao` as an in-memory database, using your models as access points to your data. 

```python
from typeyao import Model, Field

class Person(Model):
    name: str = Field(primary_key=True)
    family_name: str

for first_name in ["Snap", "Crackle", "Pop"]:
    Person(name=name, family_name="Krispies")

snap = Person.get(name="Snap")
print(snap.name) # Snap
rice_family = Person.filter(family_name="Krispies")
print([person.name for person in rice_family]) # ["Snap", "Crackle", "Pop"]
```

### Better error messages

Copy/paste the snippet below into a file and run it to see the difference in error messages between `dataclasses`, `pydantic`, and `typeyao`.

```python
import dataclasses
import pydantic
import typeyao

@dataclasses.dataclass
class DataClassPerson:
    name: str
    age: int
    sex: str

class PydanticPerson(pydantic.BaseModel):
    name: str
    age: int
    sex: str

class TypeyaoPerson(typeyao.Model):
    name: str
    age: int
    sex: str

# this won't fail, but it should have
DataClassPerson(name="J.I.", age="Age is a construct", sex=1)

# this fails
try:
    PydanticPerson(name="J.I.", age="Age is a construct", sex=1)
except pydantic.ValidationError as e:
    print(f"---- Pydantic Error Message ----")
    print(e, end="\n\n")

# this fails, but with a slightly better error message
try:
    TypeyaoPerson(name="J.I.", age="Age is a construct", sex=1)
except typeyao.base.InvalidModelError as e:
    print(f"---- Typeyao Error Message ----")
    print(e, end="\n\n")
```

The above snippet will print:
```
---- Pydantic Error Message ----
1 validation error for PydanticPerson
age
  value is not a valid integer (type=type_error.integer)

---- Typeyao Error Message ----

{
    "age": "The value 'Age is a construct' of type <class 'str'> must be of type <class 'int'>",
}

```

### Reactive fields

Let's say you have the model below:

```python
class Person:
    name: str
    age: int
    is_adult: bool
```

and you want `is_adult` to depend on the value of `age`. With `typeyao`, you can do this:

```python
from typeyao import Model

class Person(Model):
    name: str
    age: int
    is_adult: bool

    def set_is_adult(self) -> bool:
        return self.age >= 18
```

<hr>

### Why not `dataclasses` ?

#### There are better options

`pydantic` is a great library that does everything `dataclasses` does, and more. The only reason you might want to use `dataclasses` is if you're using a version of python that doesn't support `pydantic` (e.g. python 3.6) or if you don't want to add a dependency to your project.

#### `dataclasses` doesn't validate your data.

```python

from dataclasses import dataclass

@dataclass
class Person:
    name: str

p = Person(name=1)  # No error!
```

#### `dataclasses` sucks at inheritance.

Since `dataclasses` require that the attribute order be the same as the `__init__` order, it's impossible to create subclasses with additional attributes.


```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Person:
    name: str
    birthday: datetime | None = None

@dataclass
class Employee(Person):
    employee_id: int

# Raises TypeError: non-default argument 'employee_id' follows default argument
e = Employee(name="J.I.", employee_id="1") 
```

<hr>

### Why not `pydantic`?

**You *should* use [`pydantic`](https://docs.pydantic.dev/latest/)**, unless you already know why it wouldn't work. It is a much better supported library.

But here a few reasons you may prefer `typeyao` over `pydantic`.

#### `typeyao` handles nested data structures better than `pydantic`

```python
from __future__ import annotations

from pydantic import BaseModel as Model


class NestedStructure(Model):
    parent: NestedStructure | None = None


root = NestedStructure()
child1 = NestedStructure(parent=root)
child2 = NestedStructure(parent=root)

assert child1.parent == child2.parent == root  # passes
# you'd expect the following assertion to pass as well, but it's not
# because pydantic is doing some funny business under the hood
assert child1.parent is child2.parent is root  

Traceback (most recent call last):
  File "~/main.py", line 13, in <module>
    assert child1.parent is child2.parent is root
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

Switch out the `pydantic` import in the previous snippet with `from typeyao import Model` and the assertion will pass 🎉.

#### `pydantic` coerces your data. `typeyao` does not.

Type coercion is fantastic for some use cases, but very annoying when you didn't ask for it (see example below).

```python

import pydantic
import typeyao

class Person(pydantic.BaseModel):
    name: str

me = Person(name=1)  # no error! the 1 is coerced into a string
print(me.name)  # '1'

class Person(typeyao.Model):
    name: str

me = Person(name=1)  # raises a typeyao.base.InvalidModelError
```

<hr>

### What does `typeyao` mean?


It's an homage to the author's home island, Puerto Rico.

The package name `typeyao` is the phonetic spelling of how a Puerto Rican would say the word "typed".

Example:
> **English:** "These models need to be explicitly typed."
> 
> **Puerto Rican:** "Esos modelos tienen que estar 'type'iao sí o sí."
