#!/usr/bin/env bash
# Phase A: backup -> validate CSV -> schema check -> confirmed import. Creates a DRAFT only.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

for f in sql/06_timetable_core.sql scripts/import_timetable_csv.py \
         scripts/phase_a_backup.py data/timetable_3d_from_photo.csv; do
  [ -f "$f" ] || { echo "MISSING $f"; exit 1; }
done

echo "== 1/4 read-only backup"
python3 scripts/phase_a_backup.py

echo; echo "== 2/4 CSV validation (no writes)"
python3 scripts/import_timetable_csv.py data/timetable_3d_from_photo.csv --label import-3D-VI --dry-run

echo; echo "== 3/4 schema check"
if ! python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.config import supabase
supabase.table('timetable_versions').select('id').limit(1).execute()
print('timetable_versions table found')
"; then
  echo "New tables missing. Run sql/06_timetable_core.sql in the Supabase SQL editor first."
  exit 1
fi

echo
read -r -p "Type IMPORT to write the 3D draft (nothing is published): " answer
if [ "$answer" != "IMPORT" ]; then echo "Stopped. Nothing imported."; exit 0; fi

echo; echo "== 4/4 import draft"
python3 scripts/import_timetable_csv.py data/timetable_3d_from_photo.csv --label import-3D-VI

echo
echo "Verify in Supabase SQL editor (expect 33 entries, status draft):"
echo "  select v.label, v.status, count(e.id) from timetable_versions v"
echo "  left join timetable_entries e on e.version_id = v.id group by v.label, v.status;"
