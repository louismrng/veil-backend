"""Veil REST API — FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from db import close_pool, get_pool
from routes import account, groups, push, server_info, turn


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage the database connection pool lifecycle."""
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Veil Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(push.router)
app.include_router(account.router)
app.include_router(server_info.router)
app.include_router(turn.router)
app.include_router(groups.router)
