import os
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from routes import _safe_path, MAX_FILE_SIZE, ALLOWED_EXTENSIONS


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
