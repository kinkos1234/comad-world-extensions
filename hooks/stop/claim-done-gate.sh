#!/usr/bin/env bash
# claim-done-gate entrypoint. Delegates to the python implementation so
# transcript parsing stays straightforward.
exec /usr/bin/env python3 "$(dirname "$0")/claim-done-gate.py"
