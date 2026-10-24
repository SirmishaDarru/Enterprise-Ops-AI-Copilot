from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def body(code: str, message: str, request: Request, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []},
            "request_id": request.state.request_id}


async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=body(exc.code, exc.message, request))


async def http_error_handler(request: Request, exc: HTTPException):
    code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
        exc.status_code, "HTTP_ERROR"
    )
    response = JSONResponse(status_code=exc.status_code,
                            content=body(code, str(exc.detail), request))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [{"path": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422,
                        content=body("VALIDATION_ERROR", "Invalid request", request, details))
