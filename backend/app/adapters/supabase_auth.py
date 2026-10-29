"""Supabase JWT verification, using cached provider public signing keys."""
import jwt


def verify_token(token, issuer, jwks_client, secret):
    if secret:
        key = secret
        algorithms = ["HS256"]
    else:
        key = jwks_client.get_signing_key_from_jwt(token).key
        algorithms = ["ES256", "RS256"]
    claims = jwt.decode(
        token, key, algorithms=algorithms, audience="authenticated", issuer=issuer,
        options={"require": ["exp", "iss", "aud", "sub"]},
    )
    if not isinstance(claims["sub"], str) or not claims["sub"].strip():
        raise jwt.InvalidTokenError("Missing user identity")
    return claims
