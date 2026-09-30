"""CLI sharing the exact same service as MCP. Parameters are JSON, not shell code."""
import argparse
import json

from .config import Settings
from .knowledge import list_capabilities, search_knowledge
from .registry import SERVICE_TOOLS
from .service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action")
    parser.add_argument("--json", default="{}", help="JSON parameters")
    args = parser.parse_args()
    params = json.loads(args.json)
    if args.action == "capabilities":
        result = list_capabilities()
    elif args.action == "search":
        result = search_knowledge(**params)
    else:
        service = Service(Settings.from_env())
        if args.action.startswith("_") or args.action not in SERVICE_TOOLS:
            parser.error("Unknown action")
        result = getattr(service, args.action)(**params)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if isinstance(result, dict) and result.get("status") in ("failed", "partial", "uncertain", "needs_review", "completed_unverified"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
