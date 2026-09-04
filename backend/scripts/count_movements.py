"""Count the movements a document produced, for the E2E suite.

    uv run python scripts/count_movements.py <receipt-id>

Prints `batches=<n> movements=<n>`. Stock balance gets a real endpoint in Phase
6; until then the browser has no way to observe what posting actually wrote, and
"a double click produces one movement" is a claim about the database rather than
about the screen.

A script rather than an endpoint, for the same reason as
`mark_receipt_posted.py`: test-only capabilities that ship are backdoors.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.inventory import InventoryBatch, StockMovement  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: count_movements.py <receipt-id>")

    receipt_id = uuid.UUID(sys.argv[1])

    with SessionLocal() as session:
        batches = session.scalar(
            select(func.count())
            .select_from(InventoryBatch)
            .where(InventoryBatch.receipt_id == receipt_id)
        )
        movements = session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.document_id == receipt_id)
        )
        print(f"batches={batches} movements={movements}")


if __name__ == "__main__":
    main()
