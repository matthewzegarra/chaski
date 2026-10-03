"""Creates the Azure SQL users of the CHASKI managed identities (run once by the SQL Entra
admin; Azure SQL only accepts Entra authentication, so no passwords exist):

    uv run python infra/scripts/dw_users.py <sql-server-fqdn> <database> <access-token>
    (deploy.ps1 -Stage dwusers passes the values)

    id-chaski-pipeline  db_ddladmin + db_datareader + db_datawriter  (loads the DW)
    id-chaski-core      db_datareader                                (analytics)
    id-chaski-ia        db_datareader                                (NL2SQL / summaries)

Users are created WITH OBJECT_ID, so the server does not need Directory Readers in Entra.
"""

from __future__ import annotations

import json
import struct
import sys
import uuid

import pyodbc

ROLES = {
    "id-chaski-pipeline": ("db_ddladmin", "db_datareader", "db_datawriter"),
    "id-chaski-core": ("db_datareader",),
    "id-chaski-ia": ("db_datareader",),
}


def main() -> None:
    server, database, token, principals_json = sys.argv[1:5]
    principals: dict[str, str] = json.loads(principals_json)  # name -> object (principal) id
    raw = token.encode("utf-16-le")
    conn = pyodbc.connect(
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{server},1433;Database={database};Encrypt=yes;Connection Timeout=90",
        attrs_before={1256: struct.pack(f"<I{len(raw)}s", len(raw), raw)},
        autocommit=True,
    )
    cur = conn.cursor()
    for name, roles in ROLES.items():
        # Names come from ROLES and the id is validated as a UUID: no user input in the SQL.
        object_id = uuid.UUID(principals[name])
        create = f"CREATE USER [{name}] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '{object_id}'"
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = ?) "  # noqa: S608
            + create,
            name,
        )
        for role in roles:
            cur.execute(f"ALTER ROLE {role} ADD MEMBER [{name}]")
        print(f"{name}: {', '.join(roles)}")


if __name__ == "__main__":
    main()
