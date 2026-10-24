#!/usr/bin/env bash
# Создаёт нового агента из _template и регистрирует его как проект bb.
set -euo pipefail
cd "$(dirname "$0")"

slug="${1:?usage: ./new-agent.sh <slug> \"<Имя>\" \"<Роль>\"}"
name="${2:-$slug}"
role="${3:-Опиши роль агента}"
dir="agents/$slug"

[[ "$slug" =~ ^[a-z0-9-]+$ ]] || { echo "slug: только a-z, 0-9, -" >&2; exit 1; }
[[ -e "$dir" ]] && { echo "$dir уже существует" >&2; exit 1; }

cp -R _template "$dir"
find "$dir" -type f -print0 | while IFS= read -r -d '' f; do
  NAME="$name" ROLE="$role" perl -pi -e 's/\{\{AGENT_NAME\}\}/$ENV{NAME}/g; s/\{\{AGENT_ROLE\}\}/$ENV{ROLE}/g' "$f"
done

if command -v bb >/dev/null; then
  bb project create --name "$name" --root "$PWD/$dir"
else
  echo "bb не найден — зарегистрируйте проект вручную: $PWD/$dir"
fi
echo "Готово: $dir"
