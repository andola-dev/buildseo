"""FastAPI dependency providers.

The authorisation chain lives here and is the only path to a tenant-scoped
database session:

    access token → user → membership → tenant context → permission check
"""
