"""Run every query in a .sql file against the orders DB and print results as tables.
   python scripts/run_sql.py sql/queries.sql
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("TW_DB", os.path.join(ROOT, "data", "tradewatch.db"))


def show(title, cols, rows):
    print(f"\n== {title} ==")
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    print("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "sql", "queries.sql")
    text = open(path).read()
    conn = sqlite3.connect(DB)
    for block in text.split(";"):
        sql = block.strip()
        if not sql:
            continue
        m = re.search(r"--\s*(.+)", sql)
        title = m.group(1).strip() if m else sql[:50]
        cur = conn.execute(sql)
        show(title, [d[0] for d in cur.description], cur.fetchall())


if __name__ == "__main__":
    main()
