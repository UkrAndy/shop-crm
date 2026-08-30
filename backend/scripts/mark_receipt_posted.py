"""Flip one goods receipt to `posted`, for the E2E suite.

    uv run python scripts/mark_receipt_posted.py <receipt-id>

The real posting command — batch, movement, audit, idempotency — is Issue 20.
Until it exists, the read-only rendering of a posted document (Issue 17's second
acceptance criterion) still has to be provable in a browser.

**This is a script, deliberately, and not an endpoint.** A route that flips a
document's status on request is a backdoor around the entire posting
transaction; guarding it with a debug flag would only mean the backdoor ships
with the flag. Living in `scripts/` means it can never be reached over HTTP.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal  # noqa: E402
from app.models.goods_receipt import GoodsReceipt, ReceiptStatus  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: mark_receipt_posted.py <receipt-id>")

    receipt_id = uuid.UUID(sys.argv[1])

    with SessionLocal() as session:
        receipt = session.get(GoodsReceipt, receipt_id)
        if receipt is None:
            raise SystemExit(f"no receipt {receipt_id}")

        receipt.status = ReceiptStatus.POSTED
        session.commit()
        print(f"marked {receipt_id} as posted")


if __name__ == "__main__":
    main()
