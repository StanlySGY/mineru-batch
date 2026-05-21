import os
import zipfile
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from routes import _safe_path, _safe_extract_zip, _validate_external_url, require_admin, MAX_FILE_SIZE, ALLOWED_EXTENSIONS


class TestSafePath:
    def test_blocks_traversal_dotdot(self):
        with pytest.raises(HTTPException) as exc_info:
            _safe_path("../../etc/passwd")
        assert exc_info.value.status_code == 403

    def test_blocks_absolute_outside(self):
        for path in ["/tmp/evil", "/root/.ssh/id_rsa", "/etc/shadow"]:
            with pytest.raises(HTTPException) as exc_info:
                _safe_path(path)
            assert exc_info.value.status_code == 403

    def test_allows_upload_dir(self, tmp_dirs):
        with patch("routes._SAFE_DIRS", (tmp_dirs["upload"], tmp_dirs["output"], tmp_dirs["convert"])):
            result = _safe_path(os.path.join(tmp_dirs["upload"], "test.pdf"))
        assert os.path.dirname(result) == tmp_dirs["upload"]

    def test_allows_output_dir(self, tmp_dirs):
        with patch("routes._SAFE_DIRS", (tmp_dirs["upload"], tmp_dirs["output"], tmp_dirs["convert"])):
            result = _safe_path(os.path.join(tmp_dirs["output"], "test.md"))
        assert os.path.dirname(result) == tmp_dirs["output"]


class TestExternalUrlValidation:
    def test_rejects_loopback_hosts(self):
        for url in ["http://localhost:8086/file_parse", "http://127.0.0.1:8086/file_parse", "http://[::1]:8086/file_parse"]:
            with pytest.raises(HTTPException) as exc_info:
                _validate_external_url(url, "mineru_api")
            assert exc_info.value.status_code == 400

    def test_rejects_private_hosts(self):
        for url in ["http://10.0.0.1/api", "http://172.16.0.1/api", "http://192.168.1.1/api", "http://169.254.1.1/api"]:
            with pytest.raises(HTTPException) as exc_info:
                _validate_external_url(url, "mineru_api")
            assert exc_info.value.status_code == 400

    def test_rejects_invalid_scheme(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_external_url("file:///etc/passwd", "mineru_api")
        assert exc_info.value.status_code == 400


class TestZipExtraction:
    def test_blocks_zip_traversal(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.txt", "bad")
        with pytest.raises(RuntimeError) as exc_info:
            _safe_extract_zip(str(zip_path), str(dest))
        assert "ZIP 包含非法路径" in str(exc_info.value)
        assert not (tmp_path / "evil.txt").exists()

    def test_extracts_safe_zip(self, tmp_path):
        zip_path = tmp_path / "safe.zip"
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("nested/result.md", "ok")
        _safe_extract_zip(str(zip_path), str(dest))
        assert (dest / "nested" / "result.md").read_text() == "ok"


class TestAdminProtection:
    def test_allows_admin_when_key_unset(self):
        with patch("routes.ADMIN_API_KEY", ""):
            assert require_admin(None) is None

    def test_rejects_missing_admin_key(self):
        with patch("routes.ADMIN_API_KEY", "secret"):
            with pytest.raises(HTTPException) as exc_info:
                require_admin(None)
        assert exc_info.value.status_code == 401

    def test_accepts_matching_admin_key(self):
        with patch("routes.ADMIN_API_KEY", "secret"):
            assert require_admin("secret") is None

    def test_protects_destructive_endpoint(self, client):
        with patch("routes.ADMIN_API_KEY", "secret"):
            resp = client.delete("/api/logs")
            assert resp.status_code == 401
            resp = client.delete("/api/logs", headers={"X-Admin-Api-Key": "secret"})
        assert resp.status_code == 200

    def test_protects_task_mutation_endpoints(self, client, sample_task, db_session):
        sample_task.status = "failed"
        db_session.commit()
        endpoints = [
            ("post", f"/api/tasks/{sample_task.id}/cancel"),
            ("post", f"/api/tasks/{sample_task.id}/retry"),
            ("post", f"/api/tasks/{sample_task.id}/convert"),
            ("post", "/api/tasks/batch/retry?ids=1"),
            ("post", "/api/tasks/batch/convert?ids=1"),
            ("put", f"/api/tasks/{sample_task.id}/content"),
        ]
        with patch("routes.ADMIN_API_KEY", "secret"):
            for method, url in endpoints:
                resp = getattr(client, method)(url, headers={"X-Admin-Api-Key": "wrong"})
                assert resp.status_code == 401

    def test_accepts_authorized_retry(self, client, sample_task, db_session):
        sample_task.status = "failed"
        db_session.commit()
        with patch("routes.ADMIN_API_KEY", "secret"), patch("routes._enqueue_task"):
            resp = client.post(f"/api/tasks/{sample_task.id}/retry", headers={"X-Admin-Api-Key": "secret"})
        assert resp.status_code == 200

    def test_rejects_invalid_retry_url(self, client, sample_task, db_session):
        sample_task.status = "failed"
        db_session.commit()
        with patch("routes.ADMIN_API_KEY", "secret"):
            resp = client.post(
                f"/api/tasks/{sample_task.id}/retry",
                headers={"X-Admin-Api-Key": "secret"},
                data={"mineru_api": "file:///etc/passwd"},
            )
        assert resp.status_code == 400

    def test_rejects_invalid_update_url(self, client, sample_task):
        with patch("routes.ADMIN_API_KEY", "secret"):
            resp = client.put(
                f"/api/tasks/{sample_task.id}",
                headers={"X-Admin-Api-Key": "secret"},
                data={"server_url": "file:///etc/passwd"},
            )
        assert resp.status_code == 400


class TestUploadValidation:
    def test_rejects_disallowed_extension(self, client):
        resp = client.post("/api/upload", files=[
            ("files", ("malware.exe", b"payload", "application/octet-stream")),
        ])
        assert resp.status_code == 400
        assert "不支持的文件类型" in resp.json()["detail"]

    def test_rejects_oversized_file(self, client):
        big = b"x" * 101
        with patch("routes.MAX_FILE_SIZE", 100):
            resp = client.post("/api/upload", files=[
                ("files", ("big.pdf", big, "application/pdf")),
            ])
        assert resp.status_code == 400
        assert "大小限制" in resp.json()["detail"]

    def test_rejects_invalid_output_format(self, client):
        resp = client.post("/api/upload",
            files=[("files", ("test.pdf", b"%PDF", "application/pdf"))],
            data={"output_format": "xml"},
        )
        assert resp.status_code == 400
