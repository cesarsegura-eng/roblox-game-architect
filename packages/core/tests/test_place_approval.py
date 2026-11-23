from core.place_approval import sign_place_publish_approval, verify_place_publish_approval

TEST_SIGNING_KEY = "rga-place-publish-approval-test-secret-32-chars"


def _values() -> dict[str, object]:
    return {
        "request_id": "12345678-1234-4234-8234-123456789abc",
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "artifact_sha256": "a" * 64,
        "universe_id": "1234",
        "place_id": "5678",
        "expires_at": 1200,
    }


def test_place_publish_approval_binds_digest_and_fixed_target():
    values = _values()
    signature = sign_place_publish_approval(TEST_SIGNING_KEY, **values)
    assert verify_place_publish_approval(TEST_SIGNING_KEY, signature, **values, now=1000)
    assert not verify_place_publish_approval(
        TEST_SIGNING_KEY, signature, **{**values, "place_id": "9999"}, now=1000
    )
    assert not verify_place_publish_approval(
        TEST_SIGNING_KEY, signature, **{**values, "artifact_sha256": "b" * 64}, now=1000
    )
    assert not verify_place_publish_approval(TEST_SIGNING_KEY, signature, **values, now=1200)


def test_place_publish_approval_rejects_noncanonical_ids_and_short_secrets():
    values = _values()
    try:
        sign_place_publish_approval(TEST_SIGNING_KEY, **{**values, "request_id": "not-a-uuid"})
    except ValueError as exc:
        assert "UUID" in str(exc)
    else:
        raise AssertionError("invalid request ID was signed")
    try:
        sign_place_publish_approval("short", **values)
    except ValueError as exc:
        assert "secret" in str(exc)
    else:
        raise AssertionError("short secret was accepted")
