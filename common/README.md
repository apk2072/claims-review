# common

Shared SQLAlchemy models (`claims`, `extractions`, `reviews`, `review_metrics`, `agent_memory`) and Alembic migrations, used by `pipeline`, `backend`, and `agent`.

## Schema

- **`claims`** — one row per ingested document (bronze-layer identity)
- **`bronze_parses`** — raw Textract parse result per claim (trimmed blocks + per-document parse confidence); written directly over the RDS Data API by the bronze pipeline Lambda, not through this ORM — see `infra/README.md`
- **`extractions`** — gold-layer extraction result: fields, confidence scores, auto-verdict routing
- **`reviews`** — one row per reviewer verdict action; insert-only, this table IS the audit trail
- **`review_metrics`** — per-reviewer, per-day aggregate, incremented alongside each `reviews` insert
- **`agent_memory`** — long-term, per-user agent memory with pgvector similarity search (HNSW index, cosine distance)

## Running migrations

Aurora has **no public endpoint** (isolated subnet, by design — see `infra/README.md`), so Alembic connects over the **RDS Data API** instead of a direct `psycopg` connection. That needs three environment variables (the driver, `aurora-data-api`, reads them itself — no need to build a connection string):

```bash
export AURORA_CLUSTER_ARN=$(aws rds describe-db-clusters --region us-east-1 \
  --query "DBClusters[?contains(DBClusterIdentifier, 'auroracluster')].DBClusterArn" --output text)
export AURORA_SECRET_ARN=<AuroraSecretArn from cdk deploy outputs>
export AURORA_DATABASE_NAME=claims_review   # optional, this is the default

uv run --package common alembic upgrade head
```

**Known limitation**: `alembic revision --autogenerate` does **not** work against the Data API — its schema-reflection query hits `UnsupportedResultException` (Data API can't serialize the `CHAR` result type that `information_schema.columns` reflection produces). Not an issue for a from-scratch migration; write `op.create_table(...)` by hand for new migrations too, or stand up a throwaway local Postgres to autogenerate against and then adapt the output.

**pgvector + Data API gotcha**: bind parameters sent through the Data API skip Postgres's normal type-OID negotiation, so an un-cast `vector` parameter arrives as plain text and inserts fail with `column "embedding" is of type vector but expression is of type text`. Fixed by using `common.models.Vector` (not `pgvector.sqlalchemy.Vector` directly) — it adds an explicit `::vector` cast on bind. Harmless for real `psycopg` connections (backend/agent), so use it everywhere.

Expect a `DatabaseResumingException` on the first call after the cluster has been idle (scale-to-zero) — retry after ~15s.

## Tests

```bash
export AURORA_CLUSTER_ARN=... AURORA_SECRET_ARN=... AURORA_DATABASE_NAME=claims_review
uv run --package common pytest common/tests/
```

Integration test inserts one row per table and reads it back within an uncommitted transaction, then rolls back — never leaves residue in the dev cluster. Skipped automatically if `AURORA_CLUSTER_ARN` isn't set.
