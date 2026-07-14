import io
import os
import zipfile
from unittest.mock import MagicMock, patch

from models import Batch, FileTask, LogLevel, OutputFormat, ProcessLog, TaskStatus, _backfill_batches_from_tasks

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n109\n%%EOF"


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
                data={**_upload_form(), "batch_id": "batch-1", "batch_name": "测试批次"})
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) == 2
        assert {t["batch_id"] for t in tasks} == {"batch-1"}
        assert {t["batch_name"] for t in tasks} == {"测试批次"}
        assert all("api_key" not in t for t in tasks)

    def test_upload_creates_batch(self, client, db_session):
        with patch("routes._enqueue_task"):
            resp = client.post("/api/upload",
                files=[("files", ("test.pdf", MINIMAL_PDF, "application/pdf"))],
                data={**_upload_form(), "batch_id": "batch-created", "batch_name": "规范批次"})
        assert resp.status_code == 200
        batch = db_session.query(Batch).filter(Batch.batch_id == "batch-created").first()
        assert batch is not None
        assert batch.name == "规范批次"
        task = db_session.query(FileTask).filter(FileTask.batch_id == "batch-created").first()
        assert task.batch_name == "规范批次"

    def test_upload_uses_server_settings_api_key(self, client, db_session):
        client.put("/api/settings", json={
            "defaults": {},
            "mineruEndpoints": [{
                "url": "http://localhost:8086/file_parse",
                "backend": "hybrid-http-client",
                "serverUrl": "http://localhost:6002/v1",
                "enabled": True,
                "apiKey": "server-secret",
            }],
        })
        with patch("routes._enqueue_task"):
            resp = client.post("/api/upload",
                files=[("files", ("test.pdf", MINIMAL_PDF, "application/pdf"))],
                data=_upload_form())
        assert resp.status_code == 200
        task = db_session.query(FileTask).first()
        assert task.api_key == "server-secret"


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

    def test_queue_status(self, client, db_session):
        pending = FileTask(
            original_filename="wait.pdf", saved_filename="wait.pdf",
            file_path="/tmp/wait.pdf", file_size=100,
            status=TaskStatus.PENDING, output_format=OutputFormat.MD,
            priority=2,
        )
        processing = FileTask(
            original_filename="run.pdf", saved_filename="run.pdf",
            file_path="/tmp/run.pdf", file_size=100,
            status=TaskStatus.PROCESSING, output_format=OutputFormat.MD,
        )
        db_session.add_all([pending, processing])
        db_session.commit()

        resp = client.get("/api/queue/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["concurrency"] == 5
        assert data["pending"] == 1
        assert data["processing"] == 1
        assert data["available_slots"] == 4
        assert data["waiting_tasks"][0]["filename"] == "wait.pdf"
        assert data["waiting_tasks"][0]["position"] == 1

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

    def test_failure_categories(self, client, db_session):
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, error_message="timeout"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, error_message="connection refused"),
        ])
        db_session.commit()
        data = client.get("/api/reports/failures").json()
        assert data["total"] == 2
        assert {item["category"] for item in data["items"]} == {"timeout", "network"}

    def test_batch_progress_report(self, client, db_session):
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="b1", batch_name="批次1"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="b1", batch_name="批次1"),
        ])
        db_session.commit()
        data = client.get("/api/reports/batches").json()
        assert data["total"] == 1
        assert data["items"][0]["progress"] == 50.0

    def test_batch_progress_report_filters_batch_id(self, client, db_session):
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="b1"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="b2"),
        ])
        db_session.commit()
        data = client.get("/api/reports/batches", params={"batch_id": "b2"}).json()
        assert data["total"] == 1
        assert data["items"][0]["batch_id"] == "b2"
        assert data["items"][0]["failed"] == 1

    def test_batch_progress_uses_canonical_batch_name(self, client, db_session):
        db_session.add(Batch(batch_id="b1", name="规范名称"))
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="b1", batch_name="旧名称 A"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="b1", batch_name="旧名称 B"),
        ])
        db_session.commit()
        data = client.get("/api/reports/batches", params={"batch_id": "b1"}).json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["batch_name"] == "规范名称"
        assert item["completed"] == 1
        assert item["failed"] == 1

    def test_batch_progress_falls_back_to_first_task_name(self, client, db_session):
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="b1", batch_name="第一个名称"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="b1", batch_name="第二个名称"),
        ])
        db_session.commit()
        data = client.get("/api/reports/batches", params={"batch_id": "b1"}).json()
        assert data["total"] == 1
        assert data["items"][0]["batch_name"] == "第一个名称"

    def test_backfill_batches_from_legacy_tasks(self, client, db_session):
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="legacy", batch_name="历史批次"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="legacy", batch_name="其他名称"),
        ])
        db_session.commit()
        _backfill_batches_from_tasks()
        batch = db_session.query(Batch).filter(Batch.batch_id == "legacy").first()
        assert batch is not None
        assert batch.name == "历史批次"

    def test_batch_endpoints(self, client, db_session):
        db_session.add(Batch(batch_id="b1", name="接口批次"))
        db_session.add_all([
            FileTask(original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, batch_id="b1"),
            FileTask(original_filename="b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.PENDING, output_format=OutputFormat.MD, batch_id="b1"),
        ])
        db_session.commit()
        list_data = client.get("/api/batches").json()
        detail = client.get("/api/batches/b1").json()
        assert list_data["total"] == 1
        assert list_data["items"][0]["archived"] is False
        assert detail["batch_id"] == "b1"
        assert detail["batch_name"] == "接口批次"
        assert detail["archived"] is False
        assert detail["total"] == 2
        assert detail["progress"] == 50.0

    def test_update_batch_rename_and_archive(self, client, db_session):
        db_session.add(Batch(batch_id="b-edit", name="旧名称"))
        task = FileTask(
            original_filename="a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf",
            status=TaskStatus.COMPLETED, output_format=OutputFormat.MD,
            batch_id="b-edit", batch_name="旧名称",
        )
        db_session.add(task)
        db_session.commit()

        resp = client.patch("/api/batches/b-edit", json={"batch_name": "新名称", "archived": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_name"] == "新名称"
        assert data["archived"] is True
        assert db_session.query(FileTask).filter(FileTask.id == task.id).first().batch_name == "新名称"

        list_data = client.get("/api/batches").json()
        assert all(item["batch_id"] != "b-edit" for item in list_data["items"])
        archived_data = client.get("/api/batches", params={"include_archived": True}).json()
        assert any(item["batch_id"] == "b-edit" for item in archived_data["items"])

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

    def test_batch_retry_removes_output_directory(self, client, sample_task, db_session, tmp_dirs):
        out_dir = os.path.join(tmp_dirs["output"], "bundle")
        os.makedirs(out_dir)
        with open(os.path.join(out_dir, "output.md"), "w") as f:
            f.write("# Hello")
        sample_task.status = TaskStatus.COMPLETED
        sample_task.output_path = out_dir
        db_session.commit()

        with patch("routes._enqueue_task") as enqueue:
            resp = client.post("/api/tasks/batch/retry", params={"ids": str(sample_task.id)})

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert not os.path.exists(out_dir)
        enqueue.assert_called_once_with(sample_task.id)
        db_session.refresh(sample_task)
        assert sample_task.status == TaskStatus.PENDING
        assert sample_task.output_path is None

    def test_batch_retry_failed_by_batch_id(self, client, db_session, tmp_dirs):
        failed_out = os.path.join(tmp_dirs["output"], "failed-batch-1")
        completed_out = os.path.join(tmp_dirs["output"], "completed-batch-1")
        os.makedirs(failed_out)
        os.makedirs(completed_out)
        failed = FileTask(original_filename="failed.pdf", saved_filename="failed.pdf", file_path="/tmp/failed.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, output_path=failed_out, batch_id="batch-1")
        completed = FileTask(original_filename="done.pdf", saved_filename="done.pdf", file_path="/tmp/done.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=completed_out, batch_id="batch-1")
        other_failed = FileTask(original_filename="other.pdf", saved_filename="other.pdf", file_path="/tmp/other.pdf", status=TaskStatus.FAILED, output_format=OutputFormat.MD, batch_id="batch-2")
        pending = FileTask(original_filename="pending.pdf", saved_filename="pending.pdf", file_path="/tmp/pending.pdf", status=TaskStatus.PENDING, output_format=OutputFormat.MD, batch_id="batch-1")
        db_session.add_all([failed, completed, other_failed, pending])
        db_session.commit()

        with patch("routes._enqueue_task") as enqueue:
            resp = client.post("/api/tasks/batch/retry", params={"batch_id": "batch-1", "failed_only": True})

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert not os.path.exists(failed_out)
        assert os.path.exists(completed_out)
        enqueue.assert_called_once_with(failed.id)
        db_session.refresh(failed)
        db_session.refresh(completed)
        db_session.refresh(other_failed)
        db_session.refresh(pending)
        assert failed.status == TaskStatus.PENDING
        assert failed.output_path is None
        assert completed.status == TaskStatus.COMPLETED
        assert other_failed.status == TaskStatus.FAILED
        assert pending.status == TaskStatus.PENDING

    def test_batch_download_markdown_only_keeps_relative_name(self, client, db_session, tmp_dirs):
        out_dir = os.path.join(tmp_dirs["output"], "bundle")
        os.makedirs(out_dir)
        with open(os.path.join(out_dir, "output.md"), "w", encoding="utf-8") as f:
            f.write("# Hello")
        with open(os.path.join(out_dir, "middle.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        task = FileTask(
            original_filename="docs/a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf",
            status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_dir,
        )
        db_session.add(task)
        db_session.commit()

        resp = client.get("/api/tasks/batch/download-markdown", params={"ids": str(task.id)})

        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert names == ["docs/a.md"]
            assert zf.read("docs/a.md").decode() == "# Hello"

    def test_batch_download_markdown_by_batch_id_exports_completed_only(self, client, db_session, tmp_dirs):
        out_a = os.path.join(tmp_dirs["output"], "batch-a.md")
        out_b = os.path.join(tmp_dirs["output"], "batch-b.md")
        out_pending = os.path.join(tmp_dirs["output"], "batch-pending.md")
        out_other = os.path.join(tmp_dirs["output"], "batch-other.md")
        for path, content in [
            (out_a, "# A"),
            (out_b, "# B"),
            (out_pending, "# Pending"),
            (out_other, "# Other"),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        db_session.add_all([
            FileTask(original_filename="docs/a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_a, batch_id="batch-1", batch_name="资料 批次/2026"),
            FileTask(original_filename="docs/b.pdf", saved_filename="b.pdf", file_path="/tmp/b.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_b, batch_id="batch-1", batch_name="资料 批次/2026"),
            FileTask(original_filename="docs/pending.pdf", saved_filename="pending.pdf", file_path="/tmp/pending.pdf", status=TaskStatus.PENDING, output_format=OutputFormat.MD, output_path=out_pending, batch_id="batch-1", batch_name="资料 批次/2026"),
            FileTask(original_filename="docs/other.pdf", saved_filename="other.pdf", file_path="/tmp/other.pdf", status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_other, batch_id="batch-2"),
        ])
        db_session.commit()

        resp = client.get("/api/tasks/batch/download-markdown", params={"batch_id": "batch-1"})

        assert resp.status_code == 200
        content_disposition = resp.headers["content-disposition"]
        assert "filename=easy_dataset_markdown_2026.zip" in content_disposition
        assert "filename*=UTF-8''easy_dataset_markdown_%E8%B5%84%E6%96%99_%E6%89%B9%E6%AC%A1_2026.zip" in content_disposition
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert names == ["docs/a.md", "docs/b.md"]
            assert zf.read("docs/a.md").decode() == "# A"
            assert zf.read("docs/b.md").decode() == "# B"

    def test_batch_download_markdown_filename_uses_batch_name(self, client, db_session, tmp_dirs):
        out_path = os.path.join(tmp_dirs["output"], "canonical.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Canonical")
        db_session.add(Batch(batch_id="batch-1", name="规范 批次/2026"))
        db_session.add(FileTask(
            original_filename="docs/a.pdf", saved_filename="a.pdf", file_path="/tmp/a.pdf",
            status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_path,
            batch_id="batch-1", batch_name="旧名称",
        ))
        db_session.commit()

        resp = client.get("/api/tasks/batch/download-markdown", params={"batch_id": "batch-1"})

        assert resp.status_code == 200
        content_disposition = resp.headers["content-disposition"]
        assert "filename=easy_dataset_markdown_2026.zip" in content_disposition
        assert "filename*=UTF-8''easy_dataset_markdown_%E8%A7%84%E8%8C%83_%E6%89%B9%E6%AC%A1_2026.zip" in content_disposition

    def test_batch_download_markdown_splits_large_file(self, client, db_session, tmp_dirs):
        out_path = os.path.join(tmp_dirs["output"], "large.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("a" * (1024 * 1024 + 10))
        task = FileTask(
            original_filename="large.pdf", saved_filename="large.pdf", file_path="/tmp/large.pdf",
            status=TaskStatus.COMPLETED, output_format=OutputFormat.MD, output_path=out_path,
        )
        db_session.add(task)
        db_session.commit()

        resp = client.get("/api/tasks/batch/download-markdown", params={"ids": str(task.id), "max_part_mb": 1})

        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert names == ["large.part01.md", "large.part02.md"]
            assert len(zf.read("large.part01.md")) <= 1024 * 1024

class TestPreviewDownload:
    def test_preview_pending_400(self, client, sample_task):
        resp = client.get(f"/api/tasks/{sample_task.id}/preview")
        assert resp.status_code == 400

    def test_quality_score_completed(self, client, sample_task, db_session, tmp_dirs):
        out_path = os.path.join(tmp_dirs["output"], "quality.md")
        with open(out_path, "w") as f:
            f.write("# Title\n\n" + "content " * 100)
        sample_task.status = TaskStatus.COMPLETED
        sample_task.output_path = out_path
        db_session.commit()
        resp = client.get(f"/api/tasks/{sample_task.id}/quality")
        assert resp.status_code == 200
        assert resp.json()["score"] > 0

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
