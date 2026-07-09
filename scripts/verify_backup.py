#!/usr/bin/env python3.14
"""Manuelle Backup-Restore-Verifikation.

Spielt das jüngste Backup in eine Wegwerf-DB ein, prüft die Kern-Tabellen und
räumt sie wieder ab. Beweist, dass das Backup wirklich restaurierbar ist.

    python3.14 scripts/verify_backup.py

Exit-Code 0 = OK, 1 = Backup defekt / nicht restaurierbar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import backup


def main() -> int:
    result = backup.verify_latest_backup()
    print(result["message"])
    if result.get("counts"):
        for table, n in result["counts"].items():
            print(f"  {table}: {n}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
