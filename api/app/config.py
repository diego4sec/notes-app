from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://notes:notes@localhost:5432/notes"

    # The public issuer, exactly as it appears in the token's `iss` claim.
    oidc_issuer: str = "http://localhost:8080/auth/realms/notes"

    # Where WE fetch keys from, which may be an in-cluster address the browser
    # cannot reach. Splitting these two is what makes the same image work in
    # compose and behind an ingress without an issuer mismatch.
    oidc_jwks_url: str = (
        "http://localhost:8080/auth/realms/notes/protocol/openid-connect/certs"
    )

    oidc_audience: str = "notes-api"

    # Empty in production: behind a single ingress host the SPA is same-origin.
    cors_origins: list[str] = []


settings = Settings()
