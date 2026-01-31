"""Authentication module"""
from .routes import router
from .jwt import create_access_token, decode_access_token
from .dependencies import get_current_user, get_optional_user
