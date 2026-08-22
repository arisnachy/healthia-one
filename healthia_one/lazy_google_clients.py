from __future__ import annotations


class LazyFirestoreClient:
    """Small reusable boundary that keeps ADC/network discovery out of constructors.

    A store may be freely assembled while the ASGI module imports. The first real
    persistence operation is the first moment that Application Default
    Credentials and the Firestore client are resolved.
    """

    def _configure_firestore(self, project: str | None = None) -> None:
        self._firestore_project = project
        self._firestore_module = None
        self._firestore_client = None

    @property
    def firestore(self):
        if self._firestore_module is None:
            from google.cloud import firestore

            self._firestore_module = firestore
        return self._firestore_module

    @property
    def client(self):
        if self._firestore_client is None:
            self._firestore_client = self.firestore.Client(project=self._firestore_project)
        return self._firestore_client

    @property
    def client_initialized(self) -> bool:
        return self._firestore_client is not None
