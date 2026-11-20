"""The one exception a decoder or encoder may raise (adapters.md section 3, KR-279)."""

CODES = (
    "E_TRUNCATED",
    "E_LENGTH",
    "E_TYPE",
    "E_CHECKSUM",
    "E_OVERLONG",
    "E_OVERFLOW",
    "E_FIELD",
    "E_SESSION",
)


class FeedError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        if code not in CODES:
            raise AssertionError(f"unknown feed error code {code}")
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
