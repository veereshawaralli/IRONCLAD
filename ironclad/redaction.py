"""Best-effort source/log secret masking, in addition to strict filesystem scope."""

import re

_ASSIGNMENT = re.compile(
    r"""(?i)((?:api[_-]?key|access[_-]?token|password|secret)[\w]*\s*[=:]\s*)(["'])([^"'\n]{8,})\2"""
)
_TOKENS = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b")
_BEARER = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]{16,}")
_PRIVATE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def redact(text: str) -> str:
    text = _PRIVATE.sub("[REDACTED PRIVATE KEY]", text)
    text = _ASSIGNMENT.sub(lambda m: m[1] + m[2] + "[REDACTED]" + m[2], text)
    text = _TOKENS.sub("[REDACTED TOKEN]", text)
    return _BEARER.sub(r"\1[REDACTED]", text)
