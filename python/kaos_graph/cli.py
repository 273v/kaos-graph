"""kaos-graph CLI."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("kaos-graph: High-performance graph library for KAOS")
        print("Usage: kaos-graph <command>")
        print("Commands: serve, version")
        return
    if args[0] == "version":
        from kaos_graph._rust import __version__

        print(f"kaos-graph {__version__}")
    elif args[0] == "serve":
        from kaos_graph.serve import main as serve_main

        serve_main(args[1:])
    else:
        print(f"Unknown command: {args[0]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
