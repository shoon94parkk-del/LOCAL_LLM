from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LOCAL_LLM Memory Agent"
    db_path: str = "data/memory.db"
    glm_mode: str = "mock"  # mock | playwright
    glm_url: str = ""
    glm_input_selector: str = "textarea"
    glm_submit_selector: str = ""
    glm_response_selector: str = "[data-message-author-role='assistant']"
    glm_user_data_dir: str = ".browser-profile"
    glm_headless: bool = False
    glm_timeout_ms: int = 120000
    top_k_context: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOCAL_LLM_", extra="ignore")

    def ensure_paths(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_paths()
