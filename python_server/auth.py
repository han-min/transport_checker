# auth.py
import os, secrets, time, urllib.parse, hashlib, hmac

USERNAME = os.environ.get("BOARD_USER", "admin")

# use gen_hash.py to generate these values
PASSWORD_SALT = os.environ.get("BOARD_SALT", "") # <-- edit this
PASSWORD_HASH = os.environ.get("BOARD_HASH", "") # <-- edit this

COOKIE_NAME = "board_session"
SESSION_TTL = 3600 * 24 * 7
SESSIONS = {}

def hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        bytes.fromhex(salt_hex),
        200_000
    ).hex()

def verify_password(input_password: str) -> bool:
    if not PASSWORD_HASH or "PUT_YOUR" in PASSWORD_HASH:
        print("WARNING: BOARD_HASH not set!")
        return False
    input_hash = hash_password(input_password, PASSWORD_SALT)
    # constant-time compare to prevent timing attacks
    return hmac.compare_digest(input_hash, PASSWORD_HASH)

def create_session():
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token

def get_token_from_request(handler):
    cookie = handler.headers.get('Cookie','')
    for part in cookie.split(';'):
        part=part.strip()
        if part.startswith(COOKIE_NAME+'='):
            return part.split('=',1)[1]
    return None

def is_valid_token(token):
    exp = SESSIONS.get(token)
    if not exp: return False
    if exp < time.time():
        SESSIONS.pop(token, None)
        return False
    return True

LOGIN_PAGE = b"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:system-ui;background:#0f1115;color:#e5e7eb;display:grid;place-items:center;min-height:100vh;margin:0}
.card{background:#1a1d24;border:1px solid #2a2e39;border-radius:16px;padding:28px;width:320px}
input{width:100%;padding:10px;margin:8px 0;border-radius:8px;border:1px solid #2a2e39;background:#0f1115;color:#fff;box-sizing:border-box}
button{width:100%;padding:10px;margin-top:12px;border-radius:8px;border:0;background:#22c55e;color:#052e10;font-weight:600;cursor:pointer}
</style></head><body><div class="card"><h2>Login</h2>
<form method="POST" action="/login">
<input name="username" placeholder="Username" required>
<input name="password" type="password" placeholder="Password" required>
<button type="submit">Login</button></form></div></body></html>
"""

class AuthMixin:
    def handle_auth_routes(self):
        if self.path.startswith('/login'):
            if self.command == 'GET':
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(LOGIN_PAGE)
            else:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode()
                params = urllib.parse.parse_qs(body)
                user = params.get('username',[''])[0]
                pwd = params.get('password',[''])[0]

                # check username + hash
                if user == USERNAME and verify_password(pwd):
                    token = create_session()
                    self.send_response(302)
                    self.send_header("Set-Cookie", f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}")
                    self.send_header("Location", "/")
                    self.end_headers()
                else:
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"Wrong login <a href='/login'>retry</a>")
            return True

        if self.path.startswith('/logout'):
            token = get_token_from_request(self)
            SESSIONS.pop(token, None)
            self.send_response(302)
            self.send_header("Set-Cookie", f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/login")
            self.end_headers()
            return True
        return False

    def is_authenticated(self):
        return is_valid_token(get_token_from_request(self))

    def redirect_to_login(self):
        self.send_response(302)
        self.send_header("Location", "/login")
        self.end_headers()
