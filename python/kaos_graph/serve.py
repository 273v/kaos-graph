"""Run the KAOS MCP server with graph tools.

Usage:
    # stdio (for Claude Code / Claude Desktop)
    kaos-graph-serve

    # streamable HTTP — loopback only by default
    kaos-graph-serve --http --port 8000

    # with debug logging
    kaos-graph-serve --debug

Audit A2-#12: ``--http`` is gated to loopback hosts (127.0.0.1, ::1, localhost)
unless ``--allow-remote`` is explicitly passed AND a bearer token is provided
via ``--bearer-token`` or ``KAOS_GRAPH_HTTP_BEARER_TOKEN``. The current
``KaosMCPServer`` does not yet implement bearer-token auth or per-request
size caps, so non-loopback exposure is refused at the CLI layer until those
land in kaos-mcp.
"""

from __future__ import annotations

import argparse
import sys

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})


def _is_loopback(host: str) -> bool:
    return host.lower() in _LOOPBACK_HOSTS


def main(argv: list[str] | None = None) -> None:
    """Entry point for the kaos-graph MCP server."""
    parser = argparse.ArgumentParser(description="KAOS MCP Server with graph tools")
    parser.add_argument("--http", action="store_true", help="Use streamable HTTP transport")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "Permit binding to a non-loopback host. Refused unless --bearer-token is "
            "also set; v0.1 does not yet implement request-size or CORS controls. "
            "Use stdio transport for trust-boundary deployments."
        ),
    )
    parser.add_argument(
        "--bearer-token",
        default=None,
        help=(
            "Bearer token required for non-loopback HTTP exposure. Forwarded to "
            "the MCP server when supported. Falls back to "
            "KAOS_GRAPH_HTTP_BEARER_TOKEN env var."
        ),
    )
    args = parser.parse_args(argv)

    if args.http and not _is_loopback(args.host):
        if not args.allow_remote:
            print(
                f"Refusing to bind kaos-graph-serve to non-loopback host "
                f"{args.host!r} without --allow-remote. Loopback hosts: "
                f"{sorted(_LOOPBACK_HOSTS)}. For trusted-network deployments, "
                "review audit A2-#12 and use the stdio transport.",
                file=sys.stderr,
            )
            sys.exit(2)
        # --allow-remote requires a bearer token from CLI or env
        import os

        token = args.bearer_token or os.environ.get("KAOS_GRAPH_HTTP_BEARER_TOKEN")
        if not token:
            print(
                f"--allow-remote requires a non-empty --bearer-token (or "
                f"KAOS_GRAPH_HTTP_BEARER_TOKEN env var). Refusing to bind to "
                f"{args.host!r} without authentication.",
                file=sys.stderr,
            )
            sys.exit(2)
        # NOTE: kaos-mcp 0.1.0 does not yet enforce bearer-token auth at the
        # transport layer. We refuse to start until that is wired through; the
        # token is accepted on the CLI for forward compatibility but the server
        # would not enforce it today. Until then, --allow-remote is effectively
        # disabled — surface that to the operator explicitly.
        print(
            "ERROR: --allow-remote is reserved for a future release. The "
            "current kaos-mcp transport does not enforce --bearer-token. "
            "Use stdio transport (default) or restrict --host to loopback.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        from kaos_core import KaosRuntime
        from kaos_mcp import (  # ty: ignore[unresolved-import]
            KaosMCPServer,
            KaosMCPSettings,
        )
    except ImportError as e:
        print(
            f"kaos-mcp and kaos-core are required for the MCP server: {e}\n"
            "Install with: pip install kaos-core kaos-mcp",
            file=sys.stderr,
        )
        sys.exit(1)

    from kaos_graph.tools import register_graph_tools

    runtime = KaosRuntime()
    n_tools = register_graph_tools(runtime)
    print(f"Registered {n_tools} graph tools", file=sys.stderr)

    settings = KaosMCPSettings(
        name="kaos-graph-server",
        transport="streamable-http" if args.http else "stdio",
        host=args.host,
        port=args.port,
        debug=args.debug,
    )

    server = KaosMCPServer(runtime=runtime, settings=settings)

    if args.http:
        print(f"Starting HTTP server on {args.host}:{args.port}/mcp", file=sys.stderr)
        server.run_streamable_http()
    else:
        print("Starting stdio server", file=sys.stderr)
        server.run_stdio()


if __name__ == "__main__":
    main()
