#!/usr/bin/env bash
# qa-gate-before-push entrypoint. Delegates to the python implementation.
exec /usr/bin/env python3 "$(dirname "$0")/qa-gate-before-push.py"
