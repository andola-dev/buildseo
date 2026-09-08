"""External provider abstractions.

Every integration lives behind a Protocol so the business layer depends on a
capability, never on a vendor. Nothing outside this package imports a provider
SDK or knows a vendor's wire format, which is what makes "switch this tenant
from OpenAI to Anthropic" a database change rather than a code change.

All providers are bring-your-own-key: credentials come from the tenant's own
encrypted ``credentials`` rows. There is deliberately no global API key
anywhere in the application.
"""
