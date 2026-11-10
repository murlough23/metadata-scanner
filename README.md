# MySQL Metadata Scanner

A small Python tool that connects to a MySQL database, reads its table and column metadata, profiles the data, applies simple quality rules, and writes a JSON report. I built it as a learning project to practice the kind of metadata scanning, data profiling, and automation work that data governance platforms depend on.

## What it does

1. Connects to MySQL, retrying with exponential backoff if the database is not ready.
2. Reads table and column metadata from `information_schema`.
3. Profiles each base table: exact row count, plus NULL and distinct counts for every column.
4. Applies quality rules and records any issues found.
5. Writes everything to a JSON report and logs a summary.
6. Exits with code `0` on success and `1` if any table failed to profile or the results do not reconcile.

## Quality rules

| Rule | Flags |
|---|---|
| `no_primary_key` | A base table with no primary key |
| `empty_table` | A table with zero rows |
| `all_null_column` | A nullable column that is NULL in every row |
| `mostly_null_column` | A column that is more than 50% NULL |
| `cols_rows_equal` | A column whose distinct count equals the row count (a likely unique column) |

Views are listed in the report but are not profiled.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Practice database

Any MySQL database works. For practice, I run MySQL in Docker and load the public Sakila sample database (no real data):

```bash
docker run --name sample-mysql -e MYSQL_ROOT_PASSWORD=changeme \
  -p 3306:3306 -v mysql-data:/var/lib/mysql -d mysql:8
docker exec -i sample-mysql mysql -uroot -pchangeme < sakila-db/sakila-schema.sql
docker exec -i sample-mysql mysql -uroot -pchangeme < sakila-db/sakila-data.sql
```

The password above is a throwaway for local practice only.

## Configuration

Settings come from environment variables, which can also be placed in a `.env` file (never committed):

| Variable | Default | Purpose |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | Database host |
| `DB_PORT` | `3306` | Database port |
| `DB_USER` | `root` | Database user |
| `DB_PASSWORD` | `changeme` | Database password |
| `DB_NAME` | `sakila` | Schema to scan |
| `EXCLUDE_TABLES` | [] | Optional list of table names to exclude from scan |
| `OUTPUT_FILE` | `metadata_report.json` | Where the report is written |

## Usage

```bash
python scan_metadata.py
```

The report contains a `summary` block (tables found, profiled, errors, issues, and whether the counts reconcile) and a `tables` section with each table's columns, row count, NULL and distinct counts, and any issues.

## Tests

```bash
python -m pytest -v
```

The tests cover the quality rules using hand-built data, so no database is needed. A GitHub Actions workflow (`.github/workflows/tests.yml`) runs them on every pull request and on pushes to `main`.

## Limitations and next steps

- Profiling uses full-table `COUNT(*)` queries, which would be slow on very large tables. A production scanner would sample or use database statistics.
- The reconciliation check confirms that every table was accounted for. It does not compare counts against an external source.
- Credentials come from environment variables. A production setup would use a secrets manager.
- It runs once on demand. Scheduling is a next step.
- It writes a JSON file and does not yet push results into a data catalog such as OpenMetadata or DataHub.
