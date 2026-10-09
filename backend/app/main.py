from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.services.errors import ConflictError, DomainError, NotFoundError

ERROR_STATUS: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
}


async def domain_error_handler(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    return JSONResponse(
        status_code=ERROR_STATUS.get(type(error), status.HTTP_400_BAD_REQUEST),
        content={"detail": error.message},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SIMTIS Finance API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(api_router)
    return app


app = create_app()
