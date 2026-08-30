"""Write the OpenAPI document to a file.

    uv run python scripts/export_openapi.py openapi.json

The frontend's TypeScript types are generated from this file rather than from a
running server, so contract generation is reproducible in CI without starting
one (research §609). Keys are sorted and the trailing newline is fixed, so a
regenerated file differs only when the contract actually changed — which is what
lets CI diff it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def main() -> None:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    document = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False)
    destination.write_text(document + "\n", encoding="utf-8")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
