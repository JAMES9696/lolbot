# Alembic Database Migrations Guide

**Author**: CLI 2 (Backend)
**Date**: 2025-10-07
**Status**: ✅ Production Ready
**V2.3 Deliverable**: GitOps-ready automated database migrations

---

## Overview

This project uses [Alembic](https://alembic.sqlalchemy.org/) for version-controlled, automated database schema migrations. Alembic ensures that database changes are:

- **Versioned**: Each schema change is tracked with a unique revision ID
- **Reversible**: Every migration has `upgrade()` and `downgrade()` functions
- **Automated**: CI/CD pipelines apply migrations before application deployment
- **Auditable**: Migration history is stored in the `alembic_version` table

---

## Configuration

### Environment Variables

Alembic reads the database URL from the project's `settings.py`, which loads from environment variables:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/lolbot
```

### Alembic Directory Structure

```
/Users/kim/Downloads/lolbot/
├── alembic.ini              # Alembic configuration
├── alembic/
│   ├── env.py               # Migration environment (reads DATABASE_URL from settings)
│   ├── script.py.mako       # Migration template
│   ├── versions/            # Migration scripts (version-controlled)
│   │   └── 375b918c8740_add_user_profiles_table_for_v2_2_.py
│   └── README
```

---

## Common Operations

### 1. Check Current Migration Status

```bash
poetry run alembic current
```

**Output Example:**
```
375b918c8740 (head)  # Current revision applied to database
```

### 2. Apply Pending Migrations (Upgrade)

```bash
poetry run alembic upgrade head
```

**What happens:**
- Alembic reads `DATABASE_URL` from `src/config/settings.py`
- Applies all pending migrations in order
- Updates `alembic_version` table with current revision

**CI/CD Integration:**
```yaml
# .github/workflows/deploy.yml
- name: Run Database Migrations
  run: poetry run alembic upgrade head
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### 3. Rollback to Previous Migration (Downgrade)

```bash
# Rollback 1 migration
poetry run alembic downgrade -1

# Rollback to specific revision
poetry run alembic downgrade 375b918c8740

# Rollback all migrations (⚠️ DANGEROUS)
poetry run alembic downgrade base
```

### 4. View Migration History

```bash
poetry run alembic history --verbose
```

**Output Example:**
```
Rev: 375b918c8740 (head)
Parent: <base>
Path: alembic/versions/375b918c8740_add_user_profiles_table_for_v2_2_.py

    Add user_profiles table for V2.2 personalization

    Create Date: 2025-10-07 01:04:42.968648
```

---

## Creating New Migrations

### Manual Migration (Recommended for asyncpg projects)

1. **Generate migration template:**
   ```bash
   poetry run alembic revision -m "Add new_table for feature_x"
   ```

2. **Edit the generated file** in `alembic/versions/`:
   ```python
   def upgrade() -> None:
       """Upgrade schema."""
       op.execute("""
           CREATE TABLE new_table (
               id SERIAL PRIMARY KEY,
               data JSONB NOT NULL
           );
       """)

   def downgrade() -> None:
       """Downgrade schema."""
       op.execute("DROP TABLE IF EXISTS new_table;")
   ```

3. **Test the migration:**
   ```bash
   # Apply migration
   poetry run alembic upgrade head

   # Verify schema
   psql $DATABASE_URL -c "\d new_table"

   # Test rollback
   poetry run alembic downgrade -1
   poetry run alembic upgrade head
   ```

---

## Migration Best Practices

### 1. Always Include Downgrade Logic

```python
# ✅ GOOD: Reversible migration
def upgrade() -> None:
    op.execute("CREATE TABLE users (id SERIAL PRIMARY KEY);")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
```

```python
# ❌ BAD: Non-reversible migration
def downgrade() -> None:
    pass  # No rollback logic!
```

### 2. Use IF EXISTS/IF NOT EXISTS for Idempotency

```python
# ✅ GOOD: Idempotent (can run multiple times safely)
op.execute("CREATE TABLE IF NOT EXISTS users (...);")
op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
```

```python
# ❌ BAD: Fails if table already exists
op.execute("CREATE TABLE users (...);")
```

### 3. Add Descriptive Comments

```python
def upgrade() -> None:
    """Add user_profiles table for V2.2 personalization.

    This migration supports the V2.2 user profile service by creating:
    - user_profiles table (discord_user_id PK, profile_data JSONB)
    - Index on puuid for Riot API lookups
    - Index on last_updated for staleness queries
    """
    op.execute(...)
```

### 4. Test Migrations on Staging First

```bash
# Staging environment
DATABASE_URL=postgresql://staging_host/db poetry run alembic upgrade head

# Verify application works
curl https://staging-api.example.com/health

# Then deploy to production
```

---

## Troubleshooting

### Problem: "Alembic can't locate database"

**Solution:** Ensure `.env` file exists with `DATABASE_URL`:
```bash
cp .env.example .env
# Edit .env to add DATABASE_URL
poetry run alembic upgrade head
```

### Problem: "Target database is not up to date"

**Solution:** Apply pending migrations:
```bash
poetry run alembic upgrade head
```

### Problem: "Migration failed, database is in inconsistent state"

**Solution:** Manually fix the database, then stamp the correct revision:
```bash
# Fix database manually
psql $DATABASE_URL -c "DROP TABLE IF EXISTS broken_table;"

# Mark migration as applied (without running it)
poetry run alembic stamp 375b918c8740
```

### Problem: "Need to rollback after deployment"

**Solution:** Use downgrade to revert:
```bash
# Rollback 1 migration
poetry run alembic downgrade -1

# Redeploy previous application version
git checkout v2.1.0
docker compose up -d
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy with Migrations

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: poetry install --no-dev

      - name: Run database migrations
        run: poetry run alembic upgrade head
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

      - name: Deploy application
        run: ./scripts/deploy.sh
```

### Docker Compose Integration

```yaml
# docker-compose.yml
services:
  api:
    build: .
    depends_on:
      migrations:
        condition: service_completed_successfully
    environment:
      DATABASE_URL: postgresql://db:5432/lolbot

  migrations:
    build: .
    command: poetry run alembic upgrade head
    environment:
      DATABASE_URL: postgresql://db:5432/lolbot
    depends_on:
      db:
        condition: service_healthy
```

---

## Migration History

| Revision | Date | Description | Author |
|----------|------|-------------|--------|
| `375b918c8740` | 2025-10-07 | Add user_profiles table for V2.2 personalization | CLI 2 |

---

## References

- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Project Settings](../src/config/settings.py)
- [User Profile Service](../src/core/services/user_profile_service.py)
- [V2.2 Implementation Summary](./V2_2_IMPLEMENTATION_SUMMARY.md)
