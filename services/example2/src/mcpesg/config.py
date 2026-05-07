from pydantic_settings import BaseSettings
from pathlib import Path
class Settings(BaseSettings):
    host: str = "0.0.0.0"
    server_port: int = 8080

    service_name: str = "mcpesg"
    logger_level: str = "INFO"
    fastmcp_log_level: str = "DEBUG"
    uvicorn_access_log: bool = True

    static_files_dir: Path = Path(__file__).parent.parent.parent / "statics"
    
    base_exposed_url: str = "https://mcp.serveousercontent.com"
