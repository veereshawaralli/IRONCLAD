from ironclad.redaction import redact


def test_common_credentials_are_masked():
    secret = "ghp_" + "a" * 30
    value = (
        'password="private-value-123"\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz\n'
        + secret
    )
    masked = redact(value)
    assert "private-value-123" not in masked
    assert "abcdefghijklmnopqrstuvwxyz" not in masked
    assert secret not in masked


def test_ordinary_code_not_modified():
    text = "def average(values):\n    return sum(values) / len(values)\n"
    assert redact(text) == text
