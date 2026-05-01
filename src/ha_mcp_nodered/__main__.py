"""CLI entry points for ha-mcp-nodered.

- `ha-mcp-nodered`     stdio transport (Claude Desktop, MCP Inspector, etc.)
- `ha-mcp-nodered-web` HTTP transport (web clients, Apache reverse proxy)
"""

import logging
import os
import sys

from .server import build_server

_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt=_LOG_DATE_FORMAT,
    )


def main() -> None:
    """Run server over stdio."""
    if "--version" in sys.argv or "-V" in sys.argv:
        from . import __version__

        print(f"ha-mcp-nodered {__version__}")
        sys.exit(0)

    from .config import get_settings

    settings = get_settings()
    _setup_logging(settings.log_level)
    server = build_server()
    server.run()


def main_web() -> None:
    """Run server over HTTP for web-capable MCP clients.

    Environment:
      - NODERED_URL, NODERED_USERNAME, NODERED_PASSWORD (required)
      - MCP_HOST (optional, default 127.0.0.1) — bind address. The default
        is loopback only; expose to a network by setting MCP_HOST=0.0.0.0
        (typically you'd front this with a reverse proxy regardless).
      - MCP_PORT (optional, default 8086)
      - MCP_SECRET_PATH (optional, default "/mcp")
      - LOG_LEVEL (optional, default INFO)
    """
    from .config import get_settings

    settings = get_settings()
    _setup_logging(settings.log_level)

    port_str = os.getenv("MCP_PORT", "8086")
    try:
        port = int(port_str)
    except ValueError:
        print(f"ERROR: MCP_PORT must be an integer, got {port_str!r}", file=sys.stderr)
        sys.exit(1)

    host = os.getenv("MCP_HOST", "127.0.0.1")
    path = os.getenv("MCP_SECRET_PATH", "/mcp")

    server = build_server()
    server.run(
        transport="http",
        host=host,
        port=port,
        path=path,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
