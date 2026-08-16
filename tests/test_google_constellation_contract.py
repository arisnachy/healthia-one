from healthia_one.google_constellation import (
    GrantBundle,
    GoogleAction,
    GoogleActionRequest,
    GoogleGrant,
    authorize_google_action,
    build_google_receipt,
    build_idempotency_key,
)


def grant(patient_id: str, bundle: GrantBundle) -> GoogleGrant:
    return GoogleGrant(patient_id=patient_id, bundle=bundle)


def test_maps_read_requires_location_grant_but_no_send_authorization():
    request = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_maps",
        action=GoogleAction.MAPS_SEARCH_NEARBY,
        payload={"lat": 19.45, "lng": -70.69, "type": "hospital"},
    )

    denied = authorize_google_action(request, [])
    allowed = authorize_google_action(
        request,
        [grant("patient_demo", GrantBundle.MAPS_LOCATION)],
    )

    assert denied.allowed is False
    assert denied.missing_grants == [GrantBundle.MAPS_LOCATION]
    assert allowed.allowed is True
    assert allowed.explicit_authorization_required is False


def test_calendar_freebusy_is_read_only_but_event_creation_needs_authorization():
    grants = [
        grant("patient_demo", GrantBundle.CALENDAR_READ),
        grant("patient_demo", GrantBundle.CALENDAR_WRITE),
    ]
    freebusy = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_calendar",
        action=GoogleAction.CALENDAR_FREEBUSY,
    )
    create = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_calendar",
        action=GoogleAction.CALENDAR_CREATE_EVENT,
        payload={"start": "2026-08-11T10:30:00-04:00"},
    )

    assert authorize_google_action(freebusy, grants).allowed is True
    blocked = authorize_google_action(create, grants)
    assert blocked.allowed is False
    assert blocked.explicit_authorization_required is True

    create.explicit_authorization_id = "authz_calendar_1"
    assert authorize_google_action(create, grants).allowed is True


def test_gmail_send_requires_send_grant_and_patient_authorization():
    request = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_email",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["clinic@example.org"], "subject": "Appointment request"},
    )

    no_scope = authorize_google_action(request, [])
    assert no_scope.allowed is False
    assert no_scope.missing_grants == [GrantBundle.GMAIL_SEND]

    with_scope = authorize_google_action(
        request,
        [grant("patient_demo", GrantBundle.GMAIL_SEND)],
    )
    assert with_scope.allowed is False
    assert with_scope.explicit_authorization_required is True

    request.explicit_authorization_id = "authz_email_1"
    approved = authorize_google_action(
        request,
        [grant("patient_demo", GrantBundle.GMAIL_SEND)],
    )
    assert approved.allowed is True


def test_youtube_public_search_and_upload_use_separate_permissions():
    search = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_education",
        action=GoogleAction.YOUTUBE_SEARCH,
        payload={"q": "asthma inhaler education"},
    )
    upload = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_education",
        action=GoogleAction.YOUTUBE_UPLOAD,
        payload={"title": "Health education"},
    )

    search_grant = [grant("patient_demo", GrantBundle.YOUTUBE_SEARCH)]
    assert authorize_google_action(search, search_grant).allowed is True
    assert authorize_google_action(upload, search_grant).allowed is False

    upload_grant = [grant("patient_demo", GrantBundle.YOUTUBE_UPLOAD)]
    blocked = authorize_google_action(upload, upload_grant)
    assert blocked.allowed is False
    upload.explicit_authorization_id = "authz_upload_1"
    assert authorize_google_action(upload, upload_grant).allowed is True


def test_grants_are_patient_scoped():
    request = GoogleActionRequest(
        patient_id="patient_a",
        mission_id="mission_contacts",
        action=GoogleAction.PEOPLE_READ_CONTACTS,
    )
    other_patient_grant = grant("patient_b", GrantBundle.CONTACTS_READ)

    decision = authorize_google_action(request, [other_patient_grant])

    assert decision.allowed is False
    assert decision.missing_grants == [GrantBundle.CONTACTS_READ]


def test_idempotency_key_is_stable_for_semantically_identical_payloads():
    first = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_email",
        action=GoogleAction.GMAIL_SEND,
        payload={"subject": "Hello", "to": ["a@example.org"]},
        explicit_authorization_id="authz_1",
    )
    second = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_email",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["a@example.org"], "subject": "Hello"},
        explicit_authorization_id="authz_1",
    )

    assert build_idempotency_key(first) == build_idempotency_key(second)


def test_receipt_contains_public_execution_evidence_not_private_reasoning():
    request = GoogleActionRequest(
        patient_id="patient_demo",
        mission_id="mission_email",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["clinic@example.org"]},
        explicit_authorization_id="authz_email_2",
    )

    receipt = build_google_receipt(
        request,
        status="completed",
        resource_id="gmail_message_123",
        safe_summary="Appointment inquiry sent to the selected clinic.",
        evidence_ids=["evidence_program_1"],
    )
    dumped = receipt.model_dump(mode="json")

    assert dumped["resource_id"] == "gmail_message_123"
    assert dumped["authorization_id"] == "authz_email_2"
    assert "reasoning" not in dumped
    assert "chain_of_thought" not in dumped
