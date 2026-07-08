"""Temporary Lambda used once to verify the VPC->Aurora network path.

Deliberately stdlib-only (no psycopg) since bundling a compiled driver into a
Lambda package requires Docker-based CDK asset bundling, which isn't
available on this machine. This handler only proves TCP reachability from
the private-with-egress subnet to Aurora's port 5432 across the security
group boundary — the actual risk called out in the design doc. The pgvector
extension check is done separately via the RDS Data API (see infra/README.md),
which needs no VPC attachment or driver at all.

Not part of the application — invoked manually via `aws lambda invoke` during
the aws-foundation-infra work item, then left in place as a documented debug
tool for re-checking VPC/security-group connectivity later if needed.
"""

import os
import socket
import struct

# Postgres wire protocol: the client speaks first. An SSLRequest is the
# smallest valid message a client can send — 4-byte length (8) + the
# SSLRequest special code (80877103) — and the server always replies with a
# single byte ('S' = supports SSL, 'N' = does not). Receiving either byte
# proves a real Postgres server answered, not just an open TCP port.
_SSL_REQUEST = struct.pack("!ii", 8, 80877103)


def handler(event, context):
    host = os.environ["DB_HOST"]
    port = int(os.environ["DB_PORT"])

    with socket.create_connection((host, port), timeout=10) as sock:
        sock.settimeout(10)
        sock.sendall(_SSL_REQUEST)
        reply = sock.recv(1)

    return {
        "reachable": True,
        "host": host,
        "port": port,
        "postgres_ssl_reply": reply.decode("ascii") if reply else None,
    }
