#!/usr/bin/env bash
# Install Cursor skills from this repository into a personal or project skills directory.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$repo_root/.cursor/skills"
target_dir="$HOME/.cursor/skills"
force=0
skills=()

usage() {
  cat <<'EOF'
Usage: ./install.sh [options] [skill ...]

Options:
  --project [PATH]  install into PATH/.cursor/skills (default: current directory)
  --force           overwrite skills that are already installed
  --list            list available skills and exit
  --help            show this message

With no skill names, every skill is installed.
EOF
}

available() {
  local path
  for path in "$source_dir"/*/SKILL.md; do
    [[ -f "$path" ]] || continue
    basename "$(dirname "$path")"
  done | sort
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      if [[ ${2-} && ${2-} != --* ]]; then
        target_dir="$(cd "$2" && pwd)/.cursor/skills"
        shift
      else
        target_dir="$(pwd)/.cursor/skills"
      fi
      ;;
    --force) force=1 ;;
    --list) available; exit 0 ;;
    --help|-h) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) skills+=("$1") ;;
  esac
  shift
done

if [[ ${#skills[@]} -eq 0 ]]; then
  while IFS= read -r name; do skills+=("$name"); done < <(available)
fi

if [[ "$target_dir" == "$source_dir" ]]; then
  echo "target is the source directory; nothing to do" >&2
  exit 2
fi

mkdir -p "$target_dir"
installed=0
skipped=0

for skill in "${skills[@]}"; do
  src="$source_dir/$skill"
  if [[ ! -f "$src/SKILL.md" ]]; then
    echo "unknown skill: $skill" >&2
    exit 1
  fi
  dest="$target_dir/$skill"
  if [[ -e "$dest" && $force -eq 0 ]]; then
    echo "skip     $skill (already installed; use --force to overwrite)"
    skipped=$((skipped + 1))
    continue
  fi
  rm -rf "$dest"
  cp -R "$src" "$dest"
  echo "install  $skill"
  installed=$((installed + 1))
done

echo "$installed installed, $skipped skipped -> $target_dir"
