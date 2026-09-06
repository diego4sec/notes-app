#!/usr/bin/env python3
"""End-to-end proof that the auth flow works, with no browser and no deps.

Runs the real authorization-code + PKCE flow against Keycloak, then calls the
API with the token it gets back. This is the check that catches the failures
unit tests cannot see: issuer mismatch, a missing audience mapper, a token with
no `sub`, a default role that never got granted.

    # compose (default)
    python3 scripts/verify-auth-flow.py

    # kubernetes
    KC_BASE=http://notes.localhost/auth/realms/notes \
    API_BASE=http://notes.localhost \
    REDIRECT=http://notes.localhost/ \
    USERNAME=someone PASSWORD=... python3 scripts/verify-auth-flow.py
"""
import base64
import hashlib
import html
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

KC = os.environ.get("KC_BASE", "http://localhost:8080/auth/realms/notes")
API = os.environ.get("API_BASE", "http://localhost:8000")
REDIRECT = os.environ.get("REDIRECT", "http://localhost:5173/")
USERNAME = os.environ.get("USERNAME", "dev")
PASSWORD = os.environ.get("PASSWORD", "dev")


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


verifier = b64(secrets.token_bytes(32))
challenge = b64(hashlib.sha256(verifier.encode()).digest())

# Cookies by hand on purpose: Keycloak marks its auth cookies Secure, and
# http.cookiejar then refuses to send them over http. A browser on a trustworthy
# origin does send them, so mimic the browser rather than the library.
COOKIES: dict[str, str] = {}


def remember(response) -> None:
    for header in response.headers.get_all("Set-Cookie") or []:
        name, _, rest = header.partition("=")
        COOKIES[name.strip()] = rest.split(";")[0]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


opener = urllib.request.build_opener(NoRedirect())

# 1. authorization request
query = urllib.parse.urlencode({
    "client_id": "notes-web",
    "response_type": "code",
    "redirect_uri": REDIRECT,
    "scope": "openid profile email",
    "state": secrets.token_urlsafe(8),
    "code_challenge": challenge,
    "code_challenge_method": "S256",
})
response = opener.open(f"{KC}/protocol/openid-connect/auth?{query}")
remember(response)
page = response.read().decode()
action = html.unescape(re.search(r'action="([^"]+)"', page).group(1))
print("1. login form served         OK")

# 2. submit credentials
form = urllib.parse.urlencode(
    {"username": USERNAME, "password": PASSWORD, "credentialId": ""}
).encode()
try:
    opener.open(urllib.request.Request(action, form, headers={"Cookie": "; ".join(
        f"{k}={v}" for k, v in COOKIES.items())}))
    raise SystemExit("FAIL: login returned a page instead of a redirect. Wrong "
                     "credentials, or the user does not exist yet.")
except urllib.error.HTTPError as err:
    location = err.headers.get("Location")
    if not location:
        raise SystemExit(f"FAIL: login did not redirect (HTTP {err.code}). If "
                         "Keycloak logged cookie_not_found, the browser origin "
                         "is not trustworthy and its Secure cookies were "
                         "dropped.") from None
params = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
if "code" not in params:
    raise SystemExit(f"FAIL: no code in redirect -> {location}")
print("2. authorization code issued OK")

# 3. exchange the code. No client secret anywhere: PKCE is the proof.
token = json.load(urllib.request.urlopen(urllib.request.Request(
    f"{KC}/protocol/openid-connect/token",
    urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": params["code"][0],
        "redirect_uri": REDIRECT,
        "client_id": "notes-web",
        "code_verifier": verifier,
    }).encode())))
access = token["access_token"]
claims = json.loads(base64.urlsafe_b64decode(access.split(".")[1] + "=="))
audience = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
print("3. token exchange (PKCE)     OK")
print("     iss  :", claims["iss"])
print("     aud  :", claims["aud"])
print("     sub  :", claims.get("sub"))
print("     roles:", claims.get("realm_access", {}).get("roles"))

assert claims["iss"] == KC, f"issuer mismatch: token says {claims['iss']}"
assert "notes-api" in audience, "audience mapper did not fire on notes-web"
assert "sub" in claims, "no sub claim: the client is missing the `basic` scope"
assert "notes-user" in claims.get("realm_access", {}).get("roles", []), \
    "notes-user not granted: check the default-roles composite"


def api(method: str, path: str, payload=None, bearer: str = access):
    request = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"authorization": f"Bearer {bearer}",
                 "content-type": "application/json"})
    result = urllib.request.urlopen(request)
    return result.status, json.loads(result.read() or b"null")

# 4. the API accepts it, and derives identity from the token
_, me = api("GET", "/api/me")
print("4. GET /api/me               OK ->", me["email"], me["roles"])
assert me["id"] == claims["sub"], "owner id must come from the sub claim"

# 5. a real write, then read it back through search and tags
_, note = api("POST", "/api/notes",
              {"title": "Kayak trip", "body": "pack the dry bag", "tags": ["sport"]})
_, hits = api("GET", "/api/notes?q=dry+bag")
_, tags = api("GET", "/api/tags")
print("5. create + search + tags    OK ->", [n["title"] for n in hits], tags)
assert any(n["id"] == note["id"] for n in hits), "full-text search missed the note"

# 6. nothing gets in without a valid signature
for label, bad in [("forged signature", access.rsplit(".", 1)[0] + ".AAAA"),
                   ("garbage", "not.a.token")]:
    try:
        api("GET", "/api/notes", bearer=bad)
        raise SystemExit(f"FAIL: {label} was accepted")
    except urllib.error.HTTPError as err:
        assert err.code == 401, f"{label} gave {err.code}, expected 401"
print("6. forged tokens rejected    OK (401)")

print("\nALL CHECKS PASSED")
