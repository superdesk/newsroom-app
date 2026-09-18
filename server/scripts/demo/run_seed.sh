#!/usr/bin/env bash
# Seeds the Briefdesk Portal demo once per database, as the `seed:` entry of server/Procfile.
#
# This process must never exit. Honcho stops every process of the Procfile as soon as one of them
# ends, and the systemd unit then restarts the whole instance in a loop. Every path below
# therefore finishes in sleep_forever, including failures, and an EXIT trap catches anything that
# slips through (an unbound variable, a typo).

set -u

# Bump to seed again on a database that was already seeded.
SEED_VERSION="v2"

ADMIN_EMAIL="${PORTAL_ADMIN_EMAIL:-admin@example.com}"

ADMIN_WAIT_SECONDS=1200
POLL_SECONDS=10

# The deployment creates the admin user in the middle of its data initialisation, with a schema
# migration still to follow, so the seed gives that a moment to finish.
SETTLE_SECONDS=45

cd "$(dirname "$0")/../.." || true

log() {
    echo "[briefdesk-seed] $*"
}

SLEEPER_PID=""

# Sleeps in the background and waits for it, because a trap only runs between foreground commands
# and the process manager's TERM has to end this script at once.
sleep_forever() {
    trap 'trap - EXIT; [ -z "$SLEEPER_PID" ] || kill "$SLEEPER_PID" 2>/dev/null; exit 0' TERM INT
    while :; do
        sleep 3600 &
        SLEEPER_PID=$!
        wait "$SLEEPER_PID"
    done
}

trap 'log "unexpected exit of run_seed.sh, idling so the instance stays up"; sleep_forever' EXIT

# state marker-check | marker-write | admin-exists
state() {
    python3 - "$1" "$SEED_VERSION" "$ADMIN_EMAIL" <<'PY'
import datetime
import os
import sys

from pymongo import MongoClient

action, version, admin_email = sys.argv[1:4]
db = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=10000).get_database()

if action == "marker-check":
    sys.exit(0 if db["briefdesk_seed"].find_one({"_id": version}) else 1)

if action == "admin-exists":
    sys.exit(0 if db["users"].find_one({"email": admin_email}) else 1)

db["briefdesk_seed"].replace_one(
    {"_id": version},
    {"_id": version, "seeded_at": datetime.datetime.now(datetime.timezone.utc)},
    upsert=True,
)
PY
}

if [ "${BRIEFDESK_SEED:-1}" = "0" ]; then
    log "BRIEFDESK_SEED=0, not seeding"
    sleep_forever
fi

# Fireq exports DB_NAME next to MONGO_URI and the Docker setups of this repository do not, which
# is what tells a deployed test instance from a developer's stack. A developer's data stays
# untouched unless BRIEFDESK_SEED=1 is set or seed_portal.py is run by hand.
if [ "${BRIEFDESK_SEED:-}" != "1" ] && [ -z "${DB_NAME:-}" ]; then
    log "DB_NAME is not set, this does not look like a Fireq instance, not seeding (BRIEFDESK_SEED=1 forces it)"
    sleep_forever
fi

if [ -z "${MONGO_URI:-}" ]; then
    log "MONGO_URI is not set, so the seed marker cannot be read, not seeding"
    sleep_forever
fi

if state marker-check; then
    log "database already seeded ($SEED_VERSION), nothing to do"
    sleep_forever
fi

# The app processes are started before the deployment runs `initialize_data` and `create_user`,
# so an answering web server says nothing about the data. The admin user is what marks it ready.
log "waiting for the admin user $ADMIN_EMAIL to exist"
waited=0
until state admin-exists; do
    if [ "$waited" -ge "$ADMIN_WAIT_SECONDS" ]; then
        log "the admin user never appeared, giving up. Restart the instance to try again."
        sleep_forever
    fi
    sleep "$POLL_SECONDS"
    waited=$((waited + POLL_SECONDS))
done
log "admin user found, giving the data initialisation ${SETTLE_SECONDS}s to finish"
sleep "$SETTLE_SECONDS"

# PORTAL_URL would switch seed_portal.py to its http transport, which cannot set passwords.
unset PORTAL_URL

log "running seed_portal.py --transport local"
if python3 -u scripts/demo/seed_portal.py --transport local; then
    if state marker-write; then
        log "seeded, marker $SEED_VERSION written"
    else
        log "seeded, but the marker could not be written, so the next restart seeds again (harmless, the seed is idempotent)"
    fi
else
    log "seed_portal.py failed, see the output above. Restart the instance to try again."
fi

sleep_forever
