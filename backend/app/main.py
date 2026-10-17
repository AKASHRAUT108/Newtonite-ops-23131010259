from fastapi import FastAPI

from app.routers import auth as auth_router

app = FastAPI(title="Newtonite Ops API", version="0.2.0")

app.include_router(auth_router.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}