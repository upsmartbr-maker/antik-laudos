import os
import time
import hmac
from typing import Optional
import jwt
from fastapi import Request

# Configurações de autenticação lidas das variáveis de ambiente
ADMIN_EMAIL_DEFAULT = "upsmartbr@gmail.com"
ADMIN_PASSWORD_DEFAULT = "@Risemode22"
JWT_ALGORITHM = "HS256"
COOKIE_NAME = "antik_admin_session"
SESSION_DURATION_SECONDS = 7 * 24 * 60 * 60  # 7 dias de validade


def get_admin_credentials() -> tuple[str, str]:
    """Retorna o email e senha configurados para o administrador."""
    email = os.getenv("ADMIN_EMAIL", ADMIN_EMAIL_DEFAULT).strip()
    password = os.getenv("ADMIN_PASSWORD", ADMIN_PASSWORD_DEFAULT).strip()
    return email, password


def get_jwt_secret() -> str:
    """Retorna o segredo para assinatura de tokens JWT."""
    return os.getenv("ADMIN_JWT_SECRET", "casa_antik_admin_secret_key_2026_super_secure")


def verify_admin_credentials(email: str, password: str) -> bool:
    """Verifica se o email e a senha correspondem às credenciais do administrador."""
    expected_email, expected_password = get_admin_credentials()
    email_clean = (email or "").strip()
    password_clean = (password or "").strip()

    email_match = hmac.compare_digest(email_clean.lower(), expected_email.lower())
    pass_match = hmac.compare_digest(password_clean, expected_password)
    return email_match and pass_match


def create_admin_token(email: str) -> str:
    """Gera um token JWT assinado para o administrador com expiração."""
    now = int(time.time())
    payload = {
        "sub": email,
        "role": "admin",
        "iat": now,
        "exp": now + SESSION_DURATION_SECONDS
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_admin_token(token: Optional[str]) -> Optional[dict]:
    """Valida o token JWT e retorna o payload decodificado ou None se inválido."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("role") == "admin":
            return payload
    except Exception:
        return None
    return None


def get_current_admin(request: Request) -> Optional[dict]:
    """Obtém os dados do admin logado a partir do cookie de sessão da requisição."""
    token = request.cookies.get(COOKIE_NAME)
    return verify_admin_token(token)
