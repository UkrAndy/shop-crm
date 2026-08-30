"""Application services.

The use case owns the transaction boundary (research §382): services commit,
routers do not. Repositories, when they arrive, must not commit independently.
"""
