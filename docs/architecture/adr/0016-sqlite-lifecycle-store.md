# ADR-0016: SQLite lifecycle storage for the local API

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

The API must durably record delivery before returning work to Studio, and commit
accepted results before acknowledging them. The original local implementation
stored one JSON file per credential using atomic replacement. That design left
the storage decision provisional and depended on directory-sync behavior that
varies across platforms. The project targets a local, single-user API process;
multi-host and shared network storage are explicitly outside this decision.

## Decision

Use Python's standard-library SQLite database at `DATA_DIR/api-state.sqlite3`.
Each state load or commit opens its own connection. State writes use an explicit
transaction with `BEGIN IMMEDIATE`, `synchronous=FULL`, WAL journaling, and a
bounded busy timeout. The database key is a full SHA-256 digest of the API
credential; raw credentials are never stored in the database. Values remain
strict JSON state documents.

On first access to a credential, the store checks for its legacy hashed JSON
file. It copies the state into SQLite transactionally, then removes the old
file only after the transaction commits. SQLite becomes authoritative after
migration; leftover legacy files are harmless and can be removed manually.

## Consequences

- State transitions are committed before the service continues to send its
  protocol response, using SQLite's full synchronous commit mode.
- WAL supports concurrent readers while writes remain serialized. The database
  is suitable for one local API host, not multi-host coordination or network
  filesystems.
- Operators must back up the database together with its `-wal` and `-shm` files
  while the API is stopped, or use SQLite's online backup API. Copying only the
  main database file while the service is running is not a supported backup.
- Existing JSON state migrates on demand, preserving deployed local state.
- SQLite adds no third-party runtime dependency. Disk failure, filesystem
  semantics, and storage hardware that lies about flush completion remain
  outside the guarantees the application can make.

## Alternatives considered

- **Keep the JSON files:** simple and readable, but platform-specific directory
  durability and the absence of transaction semantics made its guarantee less
  clear.
- **External database:** appropriate for a future hosted, multi-user service,
  but adds infrastructure and credentials that do not fit the current local
  deployment model.
