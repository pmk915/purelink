from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
SUPPORTED_JWT_ALGORITHM = "HS256"


class InvalidTokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"{PASSWORD_SCHEME}"
        f"${PASSWORD_ITERATIONS}"
        f"${salt.hex()}"
        f"${derived_key.hex()}"
    )


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = hashed_password.split("$", maxsplit=3)
        if scheme != PASSWORD_SCHEME:
            return False

        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(derived_key.hex(), digest_hex)


def create_access_token(
    *,
    subject: str,
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    _ensure_algorithm(algorithm)

    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=expires_minutes)

    header = {"alg": algorithm, "typ": "JWT"}
    payload = {
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    encoded_signature = _b64url_encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(
    *,
    token: str,
    secret_key: str,
    algorithm: str,
) -> dict[str, Any]:
    _ensure_algorithm(algorithm)

    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", maxsplit=2)
    except ValueError as exc:
        raise InvalidTokenError("Malformed token.") from exc

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    try:
        signature = _b64url_decode(encoded_signature)
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidTokenError("Invalid token encoding.") from exc

    if header.get("alg") != algorithm:
        raise InvalidTokenError("Unexpected token algorithm.")

    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidTokenError("Invalid token signature.")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise InvalidTokenError("Missing token expiration.")

    if expires_at < int(datetime.now(UTC).timestamp()):
        raise InvalidTokenError("Token has expired.")

    return payload


def _ensure_algorithm(algorithm: str) -> None:
    if algorithm != SUPPORTED_JWT_ALGORITHM:
        raise ValueError(f"Unsupported JWT algorithm: {algorithm}")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("utf-8"))
