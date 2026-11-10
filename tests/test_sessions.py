from ironclad.sessions import Sessions


def test_expiry_revocation_and_key_rotation(tmp_path):
    path = tmp_path / "sessions.db"
    sessions = Sessions(path, "test-key")
    first = sessions.issue()
    second = sessions.issue()
    assert first != second
    assert sessions.valid(first)
    sessions.revoke(first)
    assert not sessions.valid(first)
    assert sessions.valid(second)
    expired = sessions.issue(lifetime=-1)
    assert not sessions.valid(expired)
    assert not Sessions(path, "rotated-key").valid(second)
