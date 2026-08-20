from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace


_LOCAL_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions?\b",
        r"\b(reveal|show|print|dump|expose)\s+(the\s+)?(system|developer)\s+(prompt|message|instructions?)\b",
        r"\b(bypass|disable|override)\s+(the\s+)?(safety|policy|guardrails?|authorization|consent)\b",
        r"\b(exfiltrate|steal|reveal)\s+(secrets?|tokens?|credentials?|api\s*keys?)\b",
        r"\bcall\s+(the\s+)?tool\s+(anyway|regardless|without\s+(approval|authorization|consent))\b",
        r"\byou\s+are\s+now\s+(developer|system|root|admin)\b",
    )
)


@dataclass(frozen=True)
class PromptSecurityDecision:
    allowed: bool
    source: str
    reason: str
    google_checked: bool = False


class ModelArmorGate:
    """Two-layer prompt-injection defense for the newest untrusted message.

    Layer 1 is deterministic and always available. Layer 2 calls Google Model
    Armor only when explicitly configured. No conversation history or system
    prompt is sent to Model Armor; only the newest untrusted user text is
    screened.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        project_id: str = "",
        location: str = "us-central1",
        template_id: str = "",
        fail_closed: bool = True,
        client=None,
    ) -> None:
        self.enabled = bool(enabled)
        self.project_id = project_id.strip()
        self.location = location.strip() or "us-central1"
        self.template_id = template_id.strip()
        self.fail_closed = bool(fail_closed)
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.project_id and self.location and self.template_id)

    @staticmethod
    def local_check(text: str) -> PromptSecurityDecision:
        candidate = str(text or "")
        for pattern in _LOCAL_INJECTION_PATTERNS:
            if pattern.search(candidate):
                return PromptSecurityDecision(
                    allowed=False,
                    source="local_policy",
                    reason="Prompt-injection pattern blocked before model execution.",
                )
        return PromptSecurityDecision(allowed=True, source="local_policy", reason="No local injection pattern matched.")

    def _google_client(self):
        if self._client is not None:
            return self._client
        from google.api_core.client_options import ClientOptions
        from google.cloud import modelarmor_v1

        self._client = modelarmor_v1.ModelArmorClient(
            transport="rest",
            client_options=ClientOptions(
                api_endpoint=f"modelarmor.{self.location}.rep.googleapis.com"
            ),
        )
        return self._client

    @staticmethod
    def _match_found(response) -> bool:
        result = getattr(response, "sanitization_result", None)
        state = getattr(result, "filter_match_state", None)
        name = getattr(state, "name", "")
        return name == "MATCH_FOUND" or str(state).endswith("MATCH_FOUND")

    def screen(self, text: str) -> PromptSecurityDecision:
        local = self.local_check(text)
        if not local.allowed:
            return local
        if not self.enabled:
            return local
        if not self.configured:
            if self.fail_closed:
                return PromptSecurityDecision(
                    allowed=False,
                    source="model_armor_config",
                    reason="Google Model Armor is enabled but not fully configured.",
                )
            return PromptSecurityDecision(
                allowed=True,
                source="model_armor_config",
                reason="Google Model Armor configuration incomplete; local policy allowed the message.",
            )

        try:
            name = f"projects/{self.project_id}/locations/{self.location}/templates/{self.template_id}"
            try:
                from google.cloud import modelarmor_v1

                request = modelarmor_v1.SanitizeUserPromptRequest(
                    name=name,
                    user_prompt_data=modelarmor_v1.DataItem(text=str(text or "")),
                )
            except ImportError:
                if self._client is None:
                    raise
                # An explicitly injected client is a test/offline adapter. The
                # production path still requires the official typed library.
                request = SimpleNamespace(name=name, user_prompt_data=SimpleNamespace(text=str(text or "")))
            response = self._google_client().sanitize_user_prompt(request=request)
        except Exception as exc:
            if self.fail_closed:
                return PromptSecurityDecision(
                    allowed=False,
                    source="google_model_armor",
                    reason=f"Model Armor screening unavailable: {type(exc).__name__}.",
                    google_checked=True,
                )
            return PromptSecurityDecision(
                allowed=True,
                source="google_model_armor",
                reason=f"Model Armor unavailable; local policy allowed message: {type(exc).__name__}.",
                google_checked=True,
            )

        if self._match_found(response):
            return PromptSecurityDecision(
                allowed=False,
                source="google_model_armor",
                reason="Google Model Armor matched a configured safety filter.",
                google_checked=True,
            )
        return PromptSecurityDecision(
            allowed=True,
            source="google_model_armor",
            reason="Google Model Armor returned no configured filter match.",
            google_checked=True,
        )
