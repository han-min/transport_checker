import getpass, hashlib

# --- PUT YOUR STATIC SALT HERE ---
# Leave empty "" to auto-generate a new one
STATIC_SALT = ""  # <-- edit this

import secrets
salt = STATIC_SALT.strip() if STATIC_SALT.strip() else secrets.token_hex(16)

password = getpass.getpass(f"Enter password to hash (using salt={salt}): ")
confirm = getpass.getpass("Confirm password: ")

if password != confirm:
    print("Passwords don't match!")
    exit(1)

hash_hex = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200_000).hex()

print("\n--- Put this in auth.py ---")
print(f'STATIC_SALT = "{salt}"')
print(f'PASSWORD_HASH = "{hash_hex}"')
