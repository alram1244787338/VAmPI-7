from flask import Response

from models.user_model import *
from app import vuln
from api_views.rate_limit import get_config_snapshot

# ---------------------------------------------------------------------------
# Track whether the database has been initialised via /createdb
# ---------------------------------------------------------------------------
db_initialized = False


def populate_db():
    global db_initialized
    db.drop_all()
    db.create_all()
    User.init_db_users()
    db_initialized = True
    response_text = '{ "message": "Database populated." }'
    response = Response(response_text, 200, mimetype='application/json')
    return response


def basic():
    response_text = '{ "message": "VAmPI the Vulnerable API", "help": "VAmPI is a vulnerable on purpose API. It was ' \
                    'created in order to evaluate the efficiency of third party tools in identifying vulnerabilities ' \
                    'in APIs but it can also be used in learning/teaching purposes.", "vulnerable":' + "{}".format(vuln) + "}"
    response = Response(response_text, 200, mimetype='application/json')
    return response


# ---------------------------------------------------------------------------
# Runtime status / health endpoint  (GET /health)
# ---------------------------------------------------------------------------
def health():
    """Return runtime status: service readiness, DB state, vulnerable mode, rate-limit config."""
    import json
    import time

    # Quick DB connectivity probe
    db_ready = False
    try:
        from sqlalchemy.sql import text as sa_text
        db.session.execute(sa_text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False

    # Consider the DB initialised if /createdb ran in this process OR the user
    # table already holds rows (e.g. a persisted sqlite file from an earlier run).
    initialized = db_initialized
    if not initialized and db_ready:
        try:
            initialized = User.query.count() > 0
        except Exception:
            initialized = False

    data = {
        "status": "ok" if db_ready else "degraded",
        "service": "ready",
        "database": {
            "initialized": initialized,
            "reachable": db_ready,
        },
        "vulnerable_mode": bool(vuln),
        "rate_limiting": get_config_snapshot(),
        "timestamp": int(time.time()),
    }
    return Response(
        json.dumps(data, indent=2),
        200,
        mimetype='application/json'
    )
