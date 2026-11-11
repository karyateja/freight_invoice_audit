"""Exporters: CSV, JSON, SQL seed + SQLite database, reports and manifest."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .schema import TABLES, ddl


def cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def jsonable(v):
    if isinstance(v, Decimal):
        return float(v)   # all stored decimals have <= 4 dp, so the float repr is exact enough to round-trip
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def sql_value(v):
    """Python value -> sqlite3 parameter."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (Decimal, date, datetime)):
        return cell(v)
    return v


def sql_literal(v) -> str:
    """Python value -> SQL literal for seed.sql (numbers unquoted, everything else quoted)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, (int, Decimal)):
        return str(v)
    return "'" + cell(v).replace("'", "''") + "'"


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([cell(r.get(c)) for c in columns])


def write_json(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("[\n")
        fh.write(",\n".join(json.dumps({c: jsonable(r.get(c)) for c in columns}, ensure_ascii=False) for r in rows))
        fh.write("\n]\n")


def write_sql(out: Path, tables: dict, seed_sql: bool = True) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    schema_sql = ddl()
    (out / "schema.sql").write_text(schema_sql, encoding="utf-8", newline="\n")
    if seed_sql:
        with open(out / "seed.sql", "w", encoding="utf-8", newline="\n") as fh:
            fh.write("-- Seed data. Load after schema.sql (SQLite):\n--   sqlite3 freight.db < schema.sql && "
                     "sqlite3 freight.db < seed.sql\nPRAGMA foreign_keys = OFF;\nBEGIN;\n")
            for t in TABLES:
                rows = tables[t.name]
                cols = ", ".join(t.columns)
                for i in range(0, len(rows), 500):
                    chunk = rows[i:i + 500]
                    vals = ",\n".join("(" + ", ".join(sql_literal(r.get(c)) for c in t.columns) + ")" for r in chunk)
                    fh.write(f"INSERT INTO {t.name} ({cols}) VALUES\n{vals};\n")
            fh.write("COMMIT;\n")
    db = out / "freight_audit.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(schema_sql)
    for t in TABLES:
        ph = ", ".join("?" for _ in t.columns)
        con.executemany(f"INSERT INTO {t.name} ({', '.join(t.columns)}) VALUES ({ph})",
                        [[sql_value(r.get(c)) for c in t.columns] for r in tables[t.name]])
    con.commit()
    con.close()
    return db


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json_doc(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, default=jsonable, ensure_ascii=False) + "\n")
