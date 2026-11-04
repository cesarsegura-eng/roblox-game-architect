"""The local API service: the only component that talks to the plugin and holds credentials.

ARCHITECTURE.md section 2. The protocol it speaks is `packages/protocol` version 1.0
(docs/protocol/README.md); the lifecycle it enforces is
docs/architecture/adr/0011-delivery-execution-and-recovery.md, which is **Proposed**.
Where that record leaves a decision open this package marks the choice it had to make
to run at all, and the decision stays open.
"""
