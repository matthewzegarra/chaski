"""NL2SQL guardrails ("Pregúntale al banco").

The generated SQL is parsed with sqlglot and rejected unless it is exactly one read-only query
over the allow-listed gold views. A LIMIT of at most 500 rows is enforced, and it runs with the
`chaski_readonly` role (SELECT on the 3 views only, 10 s statement timeout) as a second fence.
"""

from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp

ALLOWED_SCHEMA = "gold"
ALLOWED_VIEWS = frozenset({"v_rentabilidad", "v_morosidad", "v_clientes_resumen"})
MAX_ROWS = 500

_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Merge",
        "TruncateTable", "Grant", "Copy", "Into", "Set", "Lock", "Transaction", "Commit",
        "Rollback", "Pragma", "Use",
    )
    if hasattr(exp, name)
)  # fmt: skip
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
        "dblink", "dblink_exec", "lo_import", "lo_export", "set_config", "current_setting",
        "pg_terminate_backend", "pg_cancel_backend", "query_to_xml", "pg_reload_conf",
        "xp_cmdshell", "openrowset", "opendatasource", "openquery", "waitfor",
    }
)  # fmt: skip


class UnsafeSQL(ValueError):
    """The SQL is not an allowed read-only query. The message is shown to the user."""


def _function_name(node: Any) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return str(node.sql_name()).lower()


def validate_sql(sql: str, *, dialect: str = "postgres") -> str:
    """Returns the safe SQL (with LIMIT) in the target dialect, or raises UnsafeSQL."""
    if not sql or not sql.strip():
        raise UnsafeSQL("No se generó ninguna consulta")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQL("La consulta no es SQL válido") from exc
    if len(statements) != 1:
        raise UnsafeSQL("Solo se permite una sentencia")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise UnsafeSQL("Solo se permiten consultas SELECT")

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeSQL(f"Operación no permitida: {type(node).__name__.upper()}")
        if isinstance(node, exp.Func) and _function_name(node) in _FORBIDDEN_FUNCTIONS:
            raise UnsafeSQL(f"Función no permitida: {_function_name(node)}")

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    tables = list(stmt.find_all(exp.Table))
    if not tables:
        raise UnsafeSQL("La consulta debe leer alguna de las vistas permitidas")
    for table in tables:
        name = table.name.lower()
        schema = (table.db or "").lower()
        if not schema and name in cte_names:
            continue
        if name not in ALLOWED_VIEWS or (schema and schema != ALLOWED_SCHEMA) or table.catalog:
            shown = ".".join(p for p in (table.catalog, table.db, table.name) if p)
            raise UnsafeSQL(f"Tabla no permitida: {shown}")
        if not schema:
            table.set("db", exp.to_identifier(ALLOWED_SCHEMA))

    limit = stmt.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError):
            current = None
    if current is None or current > MAX_ROWS:
        stmt = stmt.limit(MAX_ROWS)

    target = "tsql" if dialect == "tsql" else "postgres"
    return str(stmt.sql(dialect=target))


def chart_for(columns: list[str], rows: list[dict[str, Any]], suggested: str) -> str:
    if suggested in ("bar", "line", "table"):
        return suggested
    return "table"
