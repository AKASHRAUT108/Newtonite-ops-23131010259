from fastapi import FastAPI

from app.routers import auth as auth_router
from app.routers import items as items_router

app = FastAPI(title="Newtonite Ops API", version="0.3.0")

app.include_router(auth_router.router)
app.include_router(items_router.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}