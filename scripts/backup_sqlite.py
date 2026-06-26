from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a timestamped backup of the local AskMarley SQLite database.")
    parser.add_argument("--db", default="instance/askmarley.db", help="Path to SQLite file")
    parser.add_argument("--out-dir", default="backups", help="Directory to write backup files")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = out_dir / f"askmarley_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
