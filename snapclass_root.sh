# snapclass_root.sh  (sourced by the other scripts; keep it next to them)
# Finds your SnapClass project and sets SNAPCLASS_ROOT. Order:
#   1. SNAPCLASS_ROOT, if you set it yourself:  export SNAPCLASS_ROOT=/path/to/project
#   2. the folder you are in, or a parent of it
#   3. a project inside the folder that holds these scripts (up to 3 levels down)
# A project is a folder with app.py and src/screens/teacher_screen.py.
_sc_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_sc_valid() { [ -f "$1/app.py" ] && [ -f "$1/src/screens/teacher_screen.py" ]; }

_sc_find() {
  if [ -n "${SNAPCLASS_ROOT:-}" ]; then
    if _sc_valid "$SNAPCLASS_ROOT"; then return 0; fi
    echo "SNAPCLASS_ROOT is '$SNAPCLASS_ROOT', but that is not a SnapClass project" >&2
    echo "(it needs app.py and src/screens/teacher_screen.py)." >&2
    return 1
  fi
  local d="$PWD"
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    if _sc_valid "$d"; then SNAPCLASS_ROOT="$d"; return 0; fi
    d="$(dirname "$d")"
  done
  local count=0 first="" list="" p dir
  while IFS= read -r p; do
    dir="$(dirname "$p")"
    if _sc_valid "$dir"; then
      count=$((count + 1))
      if [ -z "$first" ]; then first="$dir"; fi
      list="$list  $dir"$'\n'
    fi
  done < <(find "$_sc_here" -maxdepth 3 -name app.py \
      -not -path '*/.venv/*' -not -path '*/node_modules/*' -not -path '*backup*' \
      -not -path '*_misplaced*' -not -path '*_my_full*' 2>/dev/null | sort)
  if [ "$count" -eq 1 ]; then SNAPCLASS_ROOT="$first"; return 0; fi
  if [ "$count" -eq 0 ]; then
    echo "Could not find a SnapClass project near $_sc_here." >&2
    echo "cd into it and run again, or:  export SNAPCLASS_ROOT=/full/path/to/project" >&2
  else
    echo "Found $count possible projects:" >&2
    printf '%s' "$list" >&2
    echo "Pick one:  export SNAPCLASS_ROOT=/full/path/to/the/right/one   (then run again)" >&2
  fi
  return 1
}

if _sc_find; then
  export SNAPCLASS_ROOT
  _sc_branch="$(git -C "$SNAPCLASS_ROOT" branch --show-current 2>/dev/null || true)"
  echo "SnapClass project: $SNAPCLASS_ROOT${_sc_branch:+  (git branch: $_sc_branch)}"
else
  return 1 2>/dev/null || exit 1
fi
