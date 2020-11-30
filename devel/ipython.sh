#!/usr/bin/env bash

cd "$(cd "$(dirname "$0")" >/dev/null 2>&1; pwd -P)" || exit 9

# shellcheck disable=1091
source ../.envrc

poetry run ipython -i init.ipy "$@"
