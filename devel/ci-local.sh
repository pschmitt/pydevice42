#!/bin/bash

check_black() {
  poetry run black .
}

check_isort() {
  poetry run isort .
}

check_flake8() {
  poetry run flake8 .
}

check_mypy() {
  poetry run python -m mypy .
}


if [[ "${BASH_SOURCE[0]}" == "${0}" ]]
then
  cd "$(cd "$(dirname "$0")" >/dev/null 2>&1; pwd -P)/.." || exit 9

  set -ex

  case "$1" in
    black|isort|flake8|mypy)
      check_name="$1"
      shift
      "check_${check_name}" "$@"
      ;;
    *)
      echo "Running all checks"
      check_black
      check_isort
      check_flake8
      check_mypy
  esac
fi
