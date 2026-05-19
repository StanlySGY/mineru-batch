import os
import asyncio
from unittest.mock import patch, MagicMock
from models import FileTask, TaskStatus, OutputFormat, ProcessLog, LogLevel

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n109\n%%EOF"
from models import FileTask, TaskStatus, OutputFormat, ProcessLog, LogLevel


def _upload_form(overrides=None):
    data = {
        "backend": "hybrid-http-client",
        "mineru_api": "http://localhost:8086/file_parse",
        "server_url": "http://localhost:6002/v1",
        "parse_method": "auto",
        "lang_list": "ch",
        "output_format": "md",
        "timeout": "600",
    }
    if overrides:
        data.update(overrides)
    return data


class TestUpload:
    def test_single_pdf(self, client, tmp_dirs):
        with patch("routes._enqueue_task"):
            resp = client.post("/api/upload",
                files=[("files", ("test.pdf", MINIMAL_PDF, "application/pdf"))],
                data=_upload_form())
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_multiple_files(self, client, tmp_dirs):
        with patch("routes._enqueue_task"):
            resp = client.post("/api/upload",
                files=[
                    ("files", ("a.pdf", MINIMAL_PDF, "application/pdf")),
                    ("files", ("b.pdf", MINIMAL_PDF, "application/pdf")),
                ],
                data=_upload_form())
        assert resp.status_code == 200
        assert len(resp.json()["tasks"]) == 2


class TestTaskCRUD:
    def test_list_empty(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_with_data(self, client, sample_task):
        resp = client.get("/api/tasks")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["id"] == sample_task.id

    def test_list_status_filter(self, client, sample_task):
        resp = client.get("/api/tasks", params={"status": "completed"})
        assert resp.json()["total"] == 0

    def test_get_found(self, client, sample_task):
        resp = client.get(f"/api/tasks/{sample_task.id}")
        assert resp.status_code == 200
        assert resp.json()["original_filename"] == "test.pdf"

    def test_get_not_found(self, client):
        resp = client.get("/api/tasks/9999")
        assert resp.status_code == 404

    def test_delete(self, client, sample_task):
        resp = client.delete(f"/api/tasks/{sample_task.id}")
        assert resp.status_code == 200
        resp = client.get("/api/tasks")
        assert resp.json()["total"] == 0

    def test_update_fields(self, client, sample_task):
        resp = client.put(f"/api/tasks/{sample_task.id}",
            data={"output_format": "html", "timeout": "300"})
        assert resp.status_code == 200
        assert resp.json()["output_format"] == "html"
        assert resp.json()["timeout"] == 300


class TestCancelRetry:
    def test_cancel_pending(self, client, sample_task):
        resp = client.post(f"/api/tasks/{sample_task.id}/cancel")
        assert resp.status_code == 200

    def test_cancel_completed_rejected(self, client, sample_task, db_session):
        sample_task.status = TaskStatus.COMPLETED
        db_session.commit()
        resp = client.post(f"/api/tasks/{sample_task.id}/cancel")
        assert resp.status_code == 400

    def test_retry_failed(self, client, sample_task, db_session):
        sample_task.status = TaskStatus.FAILED
        db_session.commit()
        with patch("routes._enqueue_task"):
            resp = client.post(f"/api/tasks/{sample_task.id}/retry")
        assert resp.status_code == 200


class TestConcurrency:
    def test_get_default(self, client):
        resp = client.get("/api/concurrency")
        assert resp.json()["concurrency"] == 5

    def test_set_valid(self, client):
        resp = client.put("/api/concurrency", json={"concurrency": 3})
        assert resp.json()["concurrency"] == 3

    def test_set_invalid(self, client):
        resp = client.put("/api/concurrency", json={"concurrency": 99})
        assert resp.status_code == 400


class TestStatsAndLogs:
    def test_empty_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.json()["total"] == 0

    def test_stats_with_data(self, client, sample_task):
        resp = client.get("/api/stats")
        assert resp.json()["total"] == 1
        assert resp.json()["pending"] == 1

    def test_logs_crud(self, client, db_session):
        log = ProcessLog(task_id=None, level=LogLevel.INFO, message="test log")
        db_session.add(log)
        db_session.commit()
        resp = client.get("/api/logs")
        assert resp.json()["total"] == 1
        resp = client.delete("/api/logs")
        assert resp.status_code == 200


class TestBatchOperations:
    def test_batch_delete(self, client, sample_task, db_session):
        t2 = FileTask(
            original_filename="b.pdf", saved_filename="b.pdf",
            file_path="/tmp/b.pdf", file_size=100,
            status=TaskStatus.PENDING, output_format=OutputFormat.MD,
        )
        db_session.add(t2)
        db_session.commit()
        resp = client.delete("/api/tasks/batch", params={"ids": f"{sample_task.id},{t2.id}"})
        assert resp.status_code == 200
        assert client.get("/api/tasks").json()["total"] == 0

    def test_batch_retry_filters_status(self, client, sample_task, db_session):
        resp = client.post("/api/tasks/batch/retry", params={"ids": str(sample_task.id)})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0  # PENDING not retryable


class TestPreviewDownload:
    def test_preview_pending_400(self, client, sample_task):
        resp = client.get(f"/api/tasks/{sample_task.id}/preview")
        assert resp.status_code == 400

    def test_download_completed(self, client, sample_task, db_session, tmp_dirs):
        out_path = os.path.join(tmp_dirs["output"], "test.md")
        with open(out_path, "w") as f:
            f.write("# Hello")
        sample_task.status = TaskStatus.COMPLETED
        sample_task.output_path = out_path
        db_session.commit()
        resp = client.get(f"/api/tasks/{sample_task.id}/download")
        assert resp.status_code == 200
        assert b"Hello" in resp.content


class TestConnection:
    def test_connection_ok(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("routes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/test-connection",
                json={"mineru_api": "http://localhost:8086/file_parse"})
        assert resp.status_code == 200
