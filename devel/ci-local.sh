#!/bin/bash

check_black() {
  poetry run black .
}

check_isort() {
  poetry run isort .
}

check_flakehell() {
  poetry run flakehell lint --format=stat --count --max-complexity=10 --max-line-length=80
}

check_mypy() {
  poetry run python -m mypy .
}


if [[ "${BASH_SOURCE[0]}" == "${0}" ]]
then
  cd "$(cd "$(dirname "$0")" >/dev/null 2>&1; pwd -P)/.." || exit 9

  set -ex

  check_name="all"

  case "$1" in
    flake8|pyflakes|flake|lint)
      check_name="flakehell"
      shift
      ;;
    black|isort|mypy)
      check_name="$1"
      shift
      ;;
  esac

  if [[ "$check_name" == "all" ]]
  then
    echo "Running all checks" >&2
    check_black
    check_isort
    check_flakehell
    check_mypy
  else
    "check_${check_name}" "$@"
  fi
fi
