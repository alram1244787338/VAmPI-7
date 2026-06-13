from config import db
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey


class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    book_title = db.Column(db.String(128), unique=True, nullable=False)
    secret_content = db.Column(db.String(128), nullable=False)

    user_id = db.Column(db.Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="books")

    def __init__(self, book_title, secret_content, user_id=user_id):
        self.book_title = book_title
        self.secret_content = secret_content
        self.user_id = user_id

    def __repr__(self):
        return f"<User(book_title={self.book_title}, user={self.user})>"

    def json(self):
        return {'book_title': self.book_title, 'user': self.user.username}

    def json_detail(self):
        """Return detailed representation including secret and owner."""
        return {
            'id': self.id,
            'book_title': self.book_title,
            'secret': self.secret_content,
            'owner': self.user.username,
        }

    def json_summary(self):
        """Return lightweight list representation (no secret)."""
        return {
            'id': self.id,
            'book_title': self.book_title,
            'owner': self.user.username,
        }

    @staticmethod
    def get_all_books():
        return [Book.json(user) for user in Book.query.all()]

    @staticmethod
    def get_all_books_paginated(page, per_page, search=None):
        """Return paginated list of all books, optionally filtered by title keyword."""
        query = Book.query
        if search:
            query = query.filter(Book.book_title.ilike(f'%{search}%'))
        query = query.order_by(Book.id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            'books': [book.json_summary() for book in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    @staticmethod
    def get_user_books(user_id, page, per_page, search=None):
        """Return paginated list of books owned by a specific user."""
        query = Book.query.filter_by(user_id=user_id)
        if search:
            query = query.filter(Book.book_title.ilike(f'%{search}%'))
        query = query.order_by(Book.id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            'books': [book.json_detail() for book in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }
