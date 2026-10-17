from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "newtonite"
    postgres_password: str = "newtonite_dev_pw"
    postgres_db: str = "newtonite"
    postgres_host: str = "db"
    postgres_port: int = 5432

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()