"""Generate a JWT token for development/testing purposes"""

import os
from dotenv import load_dotenv
load_dotenv()

from auth.jwt import create_access_token

token = create_access_token({
    "sub": "test_user_123",
    "email": "test@example.com",
    "name": "Test User"
})

print(f"Your JWT token:\n{token}")
