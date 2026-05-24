#!/usr/bin/env bash
# Setup Python окружения для проекта.
# Предпочтительно через uv (быстрее, lock-файл). Fallback — venv+pip.

set -euo pipefail

cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
    echo "==> uv найден ($(uv --version)) — использую uv"
    uv sync --extra dev
    echo ""
    echo "✓ Окружение готово."
    echo "  Активация:  source .venv/bin/activate"
    echo "  Запуск тестов: uv run pytest"
    echo "  Запуск jupyter: uv run jupyter lab"
else
    echo "==> uv не найден — fallback на venv + pip"
    echo "    (для скорости рекомендуем установить uv: 'curl -LsSf https://astral.sh/uv/install.sh | sh')"

    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate

    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"

    echo ""
    echo "✓ Окружение готово."
    echo "  Активация:   source .venv/bin/activate"
    echo "  Запуск тестов: pytest"
    echo "  Запуск jupyter: jupyter lab"
fi
