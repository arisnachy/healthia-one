from healthia_one.pairing import DevicePairingManager, PairingError


def test_pairing_claim_and_token_validation() -> None:
    manager = DevicePairingManager(ttl_minutes=10)
    session = manager.create()
    assert len(session["code"]) == 6
    claim = manager.claim(session["code"], "phone-1", "My phone")
    assert manager.status(session["code"])["claimed"] is True
    assert manager.validate(claim["access_token"], "phone-1") is True
    assert manager.validate(claim["access_token"], "phone-2") is False


def test_pairing_code_cannot_be_claimed_by_another_device() -> None:
    manager = DevicePairingManager()
    code = manager.create()["code"]
    manager.claim(code, "phone-1", "Phone one")
    try:
        manager.claim(code, "phone-2", "Phone two")
    except PairingError as exc:
        assert "otro dispositivo" in str(exc)
    else:
        raise AssertionError("Pairing code should be single-device")
