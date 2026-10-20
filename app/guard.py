"""SQL guardrails: only a single read-only query against known tables is allowed to run."""
import sqlglot
from sqlglot import exp

from app.db import TABLES

MAX_ROWS = 1000

FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Copy, exp.Set, exp.Pragma, exp.Merge, exp.TruncateTable, exp.Attach, exp.Detach,
)
# Table functions that could read files or reach outside the loaded tables.
BLOCKED_FUNCTIONS = {"read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
                     "read_text", "read_blob", "glob", "httpfs", "sniff_csv", "query_table", "query"}


class UnsafeSQLError(ValueError):
    pass


def validate(sql: str) -> str:
    """Return a safe, row-limited version of `sql` or raise UnsafeSQLError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQLError(f"Could not parse SQL: {e}") from e
    if len(statements) != 1:
        raise UnsafeSQLError("Exactly one SQL statement is allowed.")
    tree = statements[0]

    if not isinstance(tree, exp.Query):
        raise UnsafeSQLError("Only SELECT queries are allowed.")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            raise UnsafeSQLError(f"{type(node).__name__} statements are not allowed.")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS:
                raise UnsafeSQLError(f"Function {name}() is not allowed.")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    allowed = {t.lower() for t in TABLES} | cte_names
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:  # e.g. a table function like range()
            raise UnsafeSQLError("Table functions are not allowed.")
        if name not in allowed:
            raise UnsafeSQLError(f"Unknown table: {table.name}. Available tables: {', '.join(TABLES)}")

    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="duckdb", pretty=True)
