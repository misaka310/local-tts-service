"""Backward-compatible ASGI entry point."""
from pathlib import Path
from .api.app import create_app
from .api.dependencies import LocalTTSService
from .config import load_config
from .runtime_registry import build_runtime_registry as _build_runtime_registry
from .services.health_service import check_http_health as _check_http_health, health_check_url as _health_check_url

__all__=["LocalTTSService","create_app","app"]
app=create_app()


def main() -> None:
    import uvicorn

    cfg = load_config(Path.cwd())
    uvicorn.run(app, host=cfg.host, port=cfg.port, reload=False)


if __name__ == "__main__":
    main()
