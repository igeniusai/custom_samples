import uvicorn
from pathlib import Path

from mcpesg.config import Settings


def run_server(module_name, reload:bool=False):
    settings = Settings()
    uvicorn.run(
        module_name,
        host=settings.host,
        port=settings.server_port,
        log_level=settings.logger_level.lower(),
        reload=reload,
        reload_dirs=[Path(__file__).parent],
        access_log=settings.uvicorn_access_log,
    )