"""Data access.

Repositories are the only place that builds SQL. Two rules make them the
second layer of tenant defence (RLS being the third):

* A tenant-owned repository takes its tenant from the *session*, never from a
  caller-supplied argument, so there is no parameter to forget or to pass
  wrongly.
* Every ``ORDER BY`` column is checked against a per-repository allow-list, so
  a client cannot steer ordering onto an arbitrary column.
"""
