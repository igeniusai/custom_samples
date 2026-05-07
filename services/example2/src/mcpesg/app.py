
import asyncio
import fastmcp
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mcpesg.config import Settings
from mcpesg.interfaces.mcp.esg import register_tools as add_esg_interfaces
from mcpesg.use_cases.esg import ESGUseCase
from starlette.responses import JSONResponse, RedirectResponse
from mcpesg.interfaces.rest.esg import add_rest_interfaces as add_esg_rest_interfaces

def create_app() -> FastMCP:
    settings = Settings()

    # reuse FastMCP's logger so all logs share the same handler and format.
    # FastMCP logs MCP operations (tools/list, tool calls, etc.) at DEBUG level,
    # so fastmcp_log_level must be set to DEBUG to see them.
    fastmcp.settings.log_level = settings.fastmcp_log_level
    logger = get_logger(settings.service_name)

    logger.info(f"Starting {settings.service_name} on {settings.host}:{settings.server_port}")
    logger.info(f"Assuming exposed at {settings.base_exposed_url}")

    # create both fastapi app and fastmcp instance, so we can add custom routes to the app while still using mcp for the tools
    app = FastAPI(title=settings.service_name, redirect_slashes=True)
    mcp = FastMCP(name=settings.service_name)


    @app.get("/healthcheck")
    async def _health_check():
        return JSONResponse({"status": "ok"})

    # create use cases
    esg = ESGUseCase(config=settings, logger=logger)
    # start cache
    asyncio.ensure_future(esg.warm_cache())

    # create interfaces
    add_esg_interfaces(mcp=mcp, use_case=esg, logger=logger)

    # expose also in rest
    add_esg_rest_interfaces(app=app, use_case=esg, logger=logger)

    logger.info(f"{settings.service_name} initialized successfully")
    mcp_app = mcp.http_app(path="/", stateless_http=True)  # stateless_http=True makes each request independent, so we can scale with multiple workers if needed
    app.mount("/mcp", mcp_app) 
    app.router.lifespan_context = mcp_app.lifespan
    # custom redirect 
    @app.api_route("/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
    async def _mcp_redirect():
        return RedirectResponse(url="/mcp/", status_code=308)
    
    # serve generated chart images — tools return /statics/<uuid>.png
    settings.static_files_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Serving static files from {settings.static_files_dir}")
    app.mount("/statics", StaticFiles(directory=settings.static_files_dir), name="statics")
    return app
    

app = create_app()