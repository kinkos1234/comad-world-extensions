#!/usr/bin/env bash
# no-env-commit entrypoint. Delegates to the python implementation so the
# parsing and dry-run resolution stay simple.
exec /usr/bin/env python3 "$(dirname "$0")/no-env-commit.py"
