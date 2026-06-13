from flask import Response, jsonify

from models.user_model import *
from app import vuln
from config import db
from rate_limiter import ALL_LIMITERS, RATE_LIMIT_ENABLED

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
# Runtime status / health endpoint
# ---------------------------------------------------------------------------
def health():
    """Return runtime status: service readiness, DB state, vulnerable mode, rate-limit config."""
    limiter_configs = {}
    for name, limiter in ALL_LIMITERS.items():
        limiter_configs[name] = limiter.get_config()

    # Quick DB connectivity probe
    db_ready = False
    try:
        from sqlalchemy.sql import text as sa_text
        db.session.execute(sa_text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False

    import time
    data = {
        "status": "ok" if db_ready else "degraded",
        "service": "ready",
        "database": {
            "initialized": db_initialized,
            "reachable": db_ready,
        },
        "vulnerable_mode": bool(vuln),
        "rate_limiting": {
            "globally_enabled": bool(RATE_LIMIT_ENABLED),
            "profiles": limiter_configs,
        },
        "timestamp": int(time.time()),
    }
    return Response(
        __import__('json').dumps(data, indent=2),
        200,
        mimetype='application/json'
    )
