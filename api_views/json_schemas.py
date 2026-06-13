register_user_schema = {
    "type": "object",
    "properties": {
        "username": {"type": "string", "minLength": 1},
        "password": {"type": "string", "minLength": 1},
        "email": {"type": "string", "minLength": 1}
    },
    "required": ["username", "password", "email"],
    "additionalProperties": False
}

login_user_schema = {
    "type": "object",
    "properties": {
        "username": {"type": "string", "minLength": 1},
        "password": {"type": "string", "minLength": 1}
    },
    "required": ["username", "password"],
    "additionalProperties": False
}

update_email_schema = {
    "type": "object",
    "properties": {
        "email": {"type": "string", "minLength": 1}
    },
    "required": ["email"],
    "additionalProperties": False
}

update_profile_schema = {
    "type": "object",
    "properties": {
        "email": {
            "type": "string",
            "minLength": 1,
            "pattern": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$"
        }
    },
    "additionalProperties": False,
    "minProperties": 1
}

update_password_schema = {
    "type": "object",
    "properties": {
        "old_password": {"type": "string", "minLength": 1},
        "new_password": {"type": "string", "minLength": 1},
        "confirm_password": {"type": "string", "minLength": 1}
    },
    "required": ["old_password", "new_password", "confirm_password"],
    "additionalProperties": False
}

add_book_schema = {
    "type": "object",
    "properties": {
        "book_title": {"type": "string", "minLength": 1},
        "secret": {"type": "string", "minLength": 1}
    },
    "required": ["book_title", "secret"],
    "additionalProperties": False
}
