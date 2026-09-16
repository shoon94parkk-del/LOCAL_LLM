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
    embedding_mode: str = "disabled"
    embedding_model_path: str = ""
    embedding_device: str = "cpu"
    embedding_query_prefix: str = ""
    embedding_document_prefix: str = ""
    agent_workspace: str = "data/workspace"
    agent_max_steps: int = 8
    glm_stop_selector: str = ""
    glm_stable_seconds: float = 5.0
    browser_bridge_token: str = ""
    skills_dir: str = "skills"
    agent_allowed_roots: list[str] = []
    agent_require_approval: bool = False
    agent_command_timeout: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOCAL_LLM_", extra="ignore")

    def ensure_paths(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_paths()
