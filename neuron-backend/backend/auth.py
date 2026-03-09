# neuron-backend/backend/auth.py
# JWT verification middleware for Flask.
# Supports both:
#   - New Supabase ECC (P-256) keys  → ES256  (fetched from JWKS endpoint)
#   - Legacy Supabase HS256 secret   → HS256  (SUPABASE_JWT_SECRET in .env)

import os
import functools

import jwt
from jwt import PyJWKClient
from flask import request, jsonify, g
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL        = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Supabase publishes its public signing keys at this standard endpoint
_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""

# Cache the JWKS client (fetches public keys once, caches for 1 hour)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not _JWKS_URL:
            raise RuntimeError("SUPABASE_URL is not set in .env")
        _jwks_client = PyJWKClient(_JWKS_URL, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


def verify_token(token: str) -> dict:
    """
    Decode and validate a Supabase JWT.

    1. Peek at the token header to check the algorithm.
    2. ES256 (new ECC P-256 key)  → verify via JWKS public key endpoint.
    3. HS256 (legacy shared secret) → verify via SUPABASE_JWT_SECRET.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as e:
        raise jwt.InvalidTokenError(f"Malformed token: {e}")

    alg = header.get("alg", "")

    # ── ES256: new ECC P-256 keys ────────────────────────────────────────────
    if alg == "ES256":
        client      = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload     = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
        return payload

    # ── HS256: legacy shared secret ──────────────────────────────────────────
    if alg == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise RuntimeError(
                "SUPABASE_JWT_SECRET is not set in .env — required for HS256 tokens."
            )
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload

    raise jwt.InvalidTokenError(f"Unsupported JWT algorithm: {alg}")


# ── Flask decorator ───────────────────────────────────────────────────────────

def require_auth(f):
    """
    Decorator for Flask route functions.
    Validates the Bearer JWT and stores decoded payload in `g.user`.

    Usage:
        @app.route("/agents")
        @require_auth
        def get_agents():
            user_id = g.user["sub"]   # Supabase user UUID
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[len("Bearer "):]

        try:
            payload = verify_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({"error": f"Invalid token: {e}"}), 401
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

        g.user = payload
        return f(*args, **kwargs)

    return decorated


def current_user_id() -> str | None:
    user = getattr(g, "user", None)
    return user.get("sub") if user else None