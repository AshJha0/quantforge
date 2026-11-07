"""The single error type. Codes are listed in specifications/cli-contract.md."""


class QfError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def required[T](value: T | None, field: str) -> T:
    """An optional input that an earlier check has already required. None here is E_SCHEMA."""
    if value is None:
        raise QfError("E_SCHEMA", f"{field} is missing", field)
    return value
