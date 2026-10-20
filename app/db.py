"""Read-only DuckDB database built from the RetailPulse star schema (Parquet files)."""
import threading
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TABLES = [
    "fact_sales", "fact_orders", "dim_customer", "dim_product", "dim_seller",
    "dim_geography", "dim_date", "customer_rfm", "cohort_retention",
]


class Database:
    def __init__(self, data_dir: Path = DATA_DIR, timeout_s: float = 15.0):
        self.timeout_s = timeout_s
        self.con = duckdb.connect(":memory:")
        for t in TABLES:
            self.con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{data_dir / (t + '.parquet')}')")
        # After loading, block file/network access and freeze settings so generated
        # SQL can only see the tables above.
        self.con.execute("SET enable_external_access = false")
        self.con.execute("SET lock_configuration = true")

    def query(self, sql: str) -> pd.DataFrame:
        timer = threading.Timer(self.timeout_s, self.con.interrupt)
        timer.start()
        try:
            return self.con.execute(sql).df()
        finally:
            timer.cancel()

    def columns(self, table: str) -> list[tuple[str, str]]:
        rows = self.con.execute(f"DESCRIBE {table}").fetchall()
        return [(r[0], r[1]) for r in rows]

    def distinct_values(self, table: str, column: str, max_values: int = 12) -> list | None:
        n = self.con.execute(f"SELECT COUNT(DISTINCT {column}) FROM {table}").fetchone()[0]
        if n > max_values:
            return None
        vals = self.con.execute(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY 1").fetchall()
        return [v[0] for v in vals]

    def row_count(self, table: str) -> int:
        return self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
