class Text2SQLError(Exception):
    code = "internal_error"
    status = "error"
    retryable = False


class PlanRejected(Text2SQLError):
    def __init__(self, code: str, message: str, *, status: str = "unsupported") -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class Forbidden(PlanRejected):
    def __init__(self, message: str = "Bạn không có quyền thực hiện truy vấn này.") -> None:
        super().__init__("forbidden", message, status="forbidden")


class UnsafeQuery(Text2SQLError):
    code = "query_unsafe"


class DataUnavailable(Text2SQLError):
    code = "data_unavailable"
    status = "temporarily_unavailable"
    retryable = True
