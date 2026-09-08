"""Pydantic v2 request and response schemas.

Response schemas are explicit allow-lists, never ``model_config`` reflections
of an ORM row. That is what guarantees a ``password_hash``, a refresh-token
digest or a credential ciphertext cannot reach a response body: the field
simply does not exist on the schema.
"""
