"""Background processing.

The API never blocks on long-running work (discovery, crawling, scoring, AI
generation, link verification). It enqueues a job and returns; a worker
process picks it up and re-establishes the same tenant context the request
had, so a handler is as confined by RLS as an HTTP request.
"""
