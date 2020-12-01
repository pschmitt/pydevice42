#!/usr/bin/env bash

usage() {
  echo "Usage: $(basename "$0") [CHECK]"
  echo
  echo "Valid CHECK values:"
  echo "  - all [default]"
  echo "  - black"
  echo "  - isort"
  echo "  - formatting (black + isort)"
  echo "  - flakehell"
  echo "  - mypy"
}

# shellcheck disable=2120
check_black() {
  poetry run black "$@" .
}

# shellcheck disable=2120
check_isort() {
  poetry run isort "$@" .
}

# shellcheck disable=2120
check_flakehell() {
  poetry run flakehell lint \
    --format=stat \
    --count \
    --max-complexity=10 \
    --max-line-length=80 \
    "$@"
}

# shellcheck disable=2120
check_mypy() {
  poetry run python -m mypy "$@" .
}


if [[ "${BASH_SOURCE[0]}" == "${0}" ]]
then
  # Go to project root
  cd "$(cd "$(dirname "$0")" >/dev/null 2>&1; pwd -P)/.." || exit 9

  set -e

  if [[ -n "$DEBUG" ]]
  then
    set -x
  fi

  check_name="all"

  case "$1" in
    flake8|pyflakes|flake|lint)
      check_name="flakehell"
      shift
      ;;
    mypy|types)
      check_name="mypy"
      shift
      ;;
    black|isort)
      check_name="$1"
      shift
      ;;
    format|formatting)
      check_name="formatting"
      shift
      ;;
    help|--help|h|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac

  if [[ "$check_name" == "all" ]]
  then
    echo "Running all checks" >&2
    check_black
    check_isort
    check_flakehell
    check_mypy
  elif [[ "$check_name" == "formatting" ]]
  then
    echo "Running formatting checks" >&2
    check_black
    check_isort
  else
    "check_${check_name}" "$@"
  fi
fi
