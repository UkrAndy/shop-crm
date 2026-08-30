"""Column conventions shared by every model.

Defined once so a later table cannot quietly pick a different primary-key type
or a money column that is not `numeric`. The reasoning lives here; the models
just use it.
"""

from sqlalchemy import DateTime, Numeric, Uuid

# Primary keys are UUIDs rather than sequential integers. In a multi-tenant
# system an integer id in a URL leaks row counts and invites enumeration across
# organizations; scope checks stop access but not inference. uuid4 has poor
# index locality — uuid7 is the upgrade path once the Python floor reaches 3.14,
# and it is a drop-in change because nothing depends on the value's shape.
UUID_PK = Uuid(as_uuid=True)

# Research §385: timestamps are timezone-aware, everywhere, without exception.
TIMESTAMPTZ = DateTime(timezone=True)

# Research §384 and the PRD: money is `numeric`/`Decimal`, never binary floating
# point. Two decimal places is the kopiyka; 14 digits leaves room well past any
# plausible line total. PostgreSQL *rounds* a third decimal rather than refusing
# it, so the API layer rejects sub-kopiyka input before it reaches here.
MONEY = Numeric(14, 2)
