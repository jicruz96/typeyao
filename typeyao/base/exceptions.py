class ModelException(Exception):
    pass


class ModelConstructionError(ModelException):
    pass


class ModelNotFoundError(ModelException):
    pass


class InvalidFieldError(ModelException):
    pass


class NoPrimaryKeyError(ModelException):
    pass


class DuplicateUniqueFieldValueError(Exception):
    pass


class InvalidModelError(ModelException):
    pass


class MissingRequiredFieldError(ModelException):
    pass


class NotInitiableError(ModelException):
    pass


class InvalidFieldChoiceError(ModelException):
    pass
