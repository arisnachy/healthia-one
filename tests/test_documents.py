import os
from io import BytesIO

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"

from fastapi.testclient import TestClient

from app.main import app
from healthia_one.documents import safe_filename


def test_safe_filename_blocks_path_traversal():
    assert safe_filename("../../medical report.pdf") == "medical_report.pdf"


def test_document_upload_is_indexed_and_downloadable():
    with TestClient(app) as client:
        response = client.post(
            "/api/documents/upload",
            data={"category": "consultation", "title": "Consulta sintética"},
            files={"file": ("consulta.txt", BytesIO(b"synthetic note"), "text/plain")},
        )
        assert response.status_code == 200
        document = response.json()
        listing = client.get("/api/documents").json()
        assert any(item["id"] == document["id"] for item in listing["documents"])
        download = client.get(f"/api/documents/{document['id']}/download")
        assert download.status_code == 200
        assert download.content == b"synthetic note"
        assert download.headers["content-disposition"].startswith("attachment;")
        preview = client.get(f"/api/documents/{document['id']}/download?inline=true")
        assert preview.status_code == 200
        assert preview.content == b"synthetic note"
        assert preview.headers["content-disposition"].startswith("inline;")


def test_chat_can_route_document_management():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Organiza mis documentos del expediente"})
        assert response.status_code == 200
        assert response.json()["mission"]["mission_type"] == "document_management"
