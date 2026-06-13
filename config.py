import os
import connexion
from flask import jsonify
from flask_sqlalchemy import SQLAlchemy
from connexion.exceptions import ProblemException

vuln_app = connexion.App(__name__, specification_dir='./openapi_specs')

SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(vuln_app.app.root_path, 'database/database.db')
vuln_app.app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
vuln_app.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

vuln_app.app.config['SECRET_KEY'] = 'random'
# start the db
db = SQLAlchemy(vuln_app.app)

def custom_problem_handler(error):
    # Custom error handler for clarity in structure
    response = jsonify({
        "status": "fail",
        "message": getattr(error, "detail", "An error occurred"),
    })
    response.status_code = error.status
    return response
vuln_app.add_error_handler(ProblemException, custom_problem_handler)

vuln_app.add_api('openapi3.yml')


def http_exception_handler(error):
    # Connexion/werkzeug raise their own HTTP errors (missing auth token,
    # request-body validation failures, unknown routes, ...) and render them in
    # a different shape than the rest of the API. Normalise the 4xx ones to the
    # same {status, message} envelope used everywhere else.
    response = jsonify({
        "status": "fail",
        "message": getattr(error, "description", None) or "An error occurred",
    })
    response.status_code = getattr(error, "code", 400) or 400
    return response


# Override connexion's default handler for every 4xx client-error class so book
# (and all other) endpoints stay consistent. 5xx errors are intentionally left
# alone so genuine server failures surface normally.
from werkzeug.exceptions import default_exceptions

for _status_code in default_exceptions:
    if 400 <= _status_code < 500:
        vuln_app.app.register_error_handler(_status_code, http_exception_handler)
