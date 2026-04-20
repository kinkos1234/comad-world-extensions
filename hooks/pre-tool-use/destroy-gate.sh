#!/usr/bin/env bash
# destroy-gate entrypoint. Delegates to the python implementation so that
# string-literal false-positives can be stripped reliably.
exec /usr/bin/env python3 "$(dirname "$0")/destroy-gate.py"
