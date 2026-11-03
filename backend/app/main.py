from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import initialize_database
from app import models  # noqa: F401 - registers SQLAlchemy models before create_all
from app.routes import router

settings = get_settings()
initialize_database()

frontend_origins = {settings.frontend_origin.rstrip("/")}
if settings.environment == "development":
    # Windows users commonly open Vite with either hostname. Browsers treat
    # localhost and 127.0.0.1 as different origins, so allow both in dev.
    if settings.frontend_origin.rstrip("/") == "http://localhost:5173":
        frontend_origins.add("http://127.0.0.1:5173")
    elif settings.frontend_origin.rstrip("/") == "http://127.0.0.1:5173":
        frontend_origins.add("http://localhost:5173")

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(frontend_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
