import jsonschema

from api_views.users import token_validator, error_message_helper
from config import db
from api_views.json_schemas import *
from flask import jsonify, Response, request, json
from models.user_model import User
from models.books_model import Book
from app import vuln

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 100


def _success_response(data, status_code=200):
    """Build a consistent success envelope."""
    return Response(
        json.dumps({'status': 'success', **data}),
        status_code,
        mimetype="application/json",
    )


def _paginate_params():
    """Extract and clamp page / per_page from query string."""
    try:
        page = int(request.args.get('page', DEFAULT_PAGE))
    except (TypeError, ValueError):
        page = DEFAULT_PAGE
    try:
        per_page = int(request.args.get('per_page', DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PER_PAGE
    if page < 1:
        page = DEFAULT_PAGE
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE
    search = request.args.get('search', None)
    if search is not None:
        search = search.strip() or None
    return page, per_page, search


# ---------------------------------------------------------------------------
# Existing endpoints (enhanced)
# ---------------------------------------------------------------------------

def get_all_books():
    """GET /books/v1 — list all books with optional pagination & search."""
    page, per_page, search = _paginate_params()
    result = Book.get_all_books_paginated(page, per_page, search)
    return _success_response({
        'data': result['books'],
        'pagination': {
            'total': result['total'],
            'page': result['page'],
            'per_page': result['per_page'],
            'pages': result['pages'],
        },
    })


def add_new_book():
    """POST /books/v1 — add a book under the authenticated user."""
    request_data = request.get_json(silent=True)
    if not request_data:
        return Response(
            error_message_helper("Request body must be valid JSON."),
            400, mimetype="application/json",
        )
    try:
        jsonschema.validate(request_data, add_book_schema)
    except jsonschema.exceptions.ValidationError as exc:
        return Response(
            error_message_helper(exc.message),
            400, mimetype="application/json",
        )

    resp = token_validator(request.headers.get('Authorization'))
    if "error" in resp:
        return Response(error_message_helper(resp), 401, mimetype="application/json")

    user = User.query.filter_by(username=resp['sub']).first()
    if not user:
        return Response(
            error_message_helper("User not found."),
            404, mimetype="application/json",
        )

    # Check duplicate title (globally, because DB has unique constraint)
    existing = Book.query.filter_by(book_title=request_data.get('book_title')).first()
    if existing:
        return Response(
            error_message_helper("Book with this title already exists."),
            409, mimetype="application/json",
        )

    new_book = Book(
        book_title=request_data.get('book_title'),
        secret_content=request_data.get('secret'),
        user_id=user.id,
    )
    db.session.add(new_book)
    db.session.commit()
    return _success_response(
        {'message': 'Book has been added.', 'data': new_book.json_detail()},
        201,
    )


def get_by_title(book_title):
    """GET /books/v1/{book_title} — retrieve a single book with its secret."""
    resp = token_validator(request.headers.get('Authorization'))
    if "error" in resp:
        return Response(error_message_helper(resp), 401, mimetype="application/json")

    if vuln:  # BOLA: any authenticated user can read any book
        book = Book.query.filter_by(book_title=str(book_title)).first()
    else:
        user = User.query.filter_by(username=resp['sub']).first()
        book = Book.query.filter_by(user=user, book_title=str(book_title)).first()

    if not book:
        return Response(error_message_helper("Book not found."), 404, mimetype="application/json")

    return _success_response({'data': {
        'book_title': book.book_title,
        'secret': book.secret_content,
        'owner': book.user.username,
    }})


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------

def get_my_books():
    """GET /books/v1/my — list only the authenticated user's own books."""
    resp = token_validator(request.headers.get('Authorization'))
    if "error" in resp:
        return Response(error_message_helper(resp), 401, mimetype="application/json")

    user = User.query.filter_by(username=resp['sub']).first()
    if not user:
        return Response(error_message_helper("User not found."), 404, mimetype="application/json")

    page, per_page, search = _paginate_params()
    result = Book.get_user_books(user.id, page, per_page, search)
    return _success_response({
        'data': result['books'],
        'pagination': {
            'total': result['total'],
            'page': result['page'],
            'per_page': result['per_page'],
            'pages': result['pages'],
        },
    })


def update_book(book_title):
    """PUT /books/v1/{book_title} — update title and/or secret of own book."""
    resp = token_validator(request.headers.get('Authorization'))
    if "error" in resp:
        return Response(error_message_helper(resp), 401, mimetype="application/json")

    request_data = request.get_json(silent=True)
    if not request_data:
        return Response(
            error_message_helper("Request body must be valid JSON."),
            400, mimetype="application/json",
        )
    try:
        jsonschema.validate(request_data, update_book_schema)
    except jsonschema.exceptions.ValidationError as exc:
        return Response(
            error_message_helper(exc.message),
            400, mimetype="application/json",
        )

    user = User.query.filter_by(username=resp['sub']).first()
    if not user:
        return Response(error_message_helper("User not found."), 404, mimetype="application/json")

    # Only the owner may update the book
    book = Book.query.filter_by(user=user, book_title=str(book_title)).first()
    if not book:
        return Response(error_message_helper("Book not found."), 404, mimetype="application/json")

    new_title = request_data.get('book_title')
    new_secret = request_data.get('secret')

    # If renaming, check the new title isn't already taken
    if new_title and new_title != book.book_title:
        conflict = Book.query.filter_by(book_title=new_title).first()
        if conflict:
            return Response(
                error_message_helper("A book with this title already exists."),
                409, mimetype="application/json",
            )
        book.book_title = new_title

    if new_secret:
        book.secret_content = new_secret

    db.session.commit()
    return _success_response({
        'message': 'Book updated.',
        'data': book.json_detail(),
    })


def delete_book(book_title):
    """DELETE /books/v1/{book_title} — delete own book."""
    resp = token_validator(request.headers.get('Authorization'))
    if "error" in resp:
        return Response(error_message_helper(resp), 401, mimetype="application/json")

    user = User.query.filter_by(username=resp['sub']).first()
    if not user:
        return Response(error_message_helper("User not found."), 404, mimetype="application/json")

    book = Book.query.filter_by(user=user, book_title=str(book_title)).first()
    if not book:
        return Response(error_message_helper("Book not found."), 404, mimetype="application/json")

    db.session.delete(book)
    db.session.commit()
    return _success_response({'message': 'Book deleted.'})
