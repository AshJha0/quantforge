"""The single error type. Codes are listed in specifications/cli-contract.md."""


class QfError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
