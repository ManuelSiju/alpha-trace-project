from __future__ import annotations
import re
from typing import Optional


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")


def is_email(s: str) -> bool:
    return bool(s and _EMAIL_RE.match(s))


def is_domain(s: str) -> bool:
    return bool(s and _DOMAIN_RE.match(s))


def normalize_username(u: str) -> str:
    return (u or "").strip().lstrip("@").lower()


def email_local(email: str) -> Optional[str]:
    if not is_email(email):
        return None
    return email.split("@", 1)[0]


def email_domain(email: str) -> Optional[str]:
    if not is_email(email):
        return None
    return email.split("@", 1)[1].lower()


def mask_email(email: str) -> str:
    if not is_email(email):
        return email
    local, dom = email.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{dom}"
