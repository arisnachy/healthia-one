from __future__ import annotations

# Recording-only compatibility shim. It does not alter Guardian logic.
# The research branch's PatientProfile field is `display_name`; the director
# surface used a human-friendly `name` alias. Add that alias before importing
# the surface, then pin PatientState.updated_at to the synthetic film clock so
# appointment evidence is evaluated on one coherent timeline.

from healthia_one.models import PatientProfile


def _get_name(self: PatientProfile) -> str:
    return self.display_name


def _set_name(self: PatientProfile, value: str) -> None:
    self.display_name = value


PatientProfile.name = property(_get_name, _set_name)  # type: ignore[attr-defined]

from healthia_one import guardian_director_demo as demo  # noqa: E402

_original_new_state = demo._new_state


def _fixed_new_state():
    state = _original_new_state()
    state.updated_at = demo.DEMO_NOW
    return state


demo._new_state = _fixed_new_state
demo.reset()
app = demo.app
