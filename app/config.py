from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./golden_idea.db"
    github_token: str | None = None
    builder_fit_score: int = 8
    cluster_threshold: float = 0.42

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
