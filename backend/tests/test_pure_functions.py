from routes import (
    _sanitize_filename, _is_doc_file, _build_mineru_form, _pick_endpoint, _extract_md_from_result,
)
from models import FileTask, OutputFormat, TaskStatus


class TestSanitizeFilename:
    def test_removes_special_chars(self):
        assert "_" in _sanitize_filename('my\\file:name?"test')
        assert "\\" not in _sanitize_filename("a\\b")

    def test_preserves_chinese(self):
        assert _sanitize_filename("测试文件.pdf") == "测试文件"

    def test_empty_fallback(self):
        assert _sanitize_filename("???") == "output"

    def test_strips_extension(self):
        assert _sanitize_filename("report.pdf") == "report"

    def test_collapses_underscores(self):
        result = _sanitize_filename("a   b")
        assert "__" not in result


class TestIsDocFile:
    def test_true_cases(self):
        for ext in [".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"]:
            assert _is_doc_file(f"file{ext}") is True

    def test_false_cases(self):
        for ext in [".pdf", ".png", ".jpg", ".txt", ".exe"]:
            assert _is_doc_file(f"file{ext}") is False


class TestBuildMineruForm:
    def test_booleans_as_strings(self):
        task = FileTask(
            original_filename="t.pdf", saved_filename="t.pdf", file_path="/t",
            formula_enable=True, table_enable=False,
        )
        form = _build_mineru_form(task)
        assert form["formula_enable"] == "true"
        assert form["table_enable"] == "false"

    def test_integer_fields_as_strings(self):
        task = FileTask(original_filename="t.pdf", saved_filename="t.pdf", file_path="/t", start_page_id=5, end_page_id=10)
        form = _build_mineru_form(task)
        assert form["start_page_id"] == "5"
        assert form["end_page_id"] == "10"


class TestPickEndpoint:
    def test_round_robin(self):
        import routes
        routes._rr_counter = 0
        eps = [{"url": "a", "enabled": True}, {"url": "b", "enabled": True}, {"url": "c", "enabled": True}]
        assert _pick_endpoint(eps)["url"] == "a"
        assert _pick_endpoint(eps)["url"] == "b"
        assert _pick_endpoint(eps)["url"] == "c"
        assert _pick_endpoint(eps)["url"] == "a"

    def test_skips_disabled(self):
        import routes
        routes._rr_counter = 0
        eps = [{"url": "a", "enabled": False}, {"url": "b", "enabled": True}]
        assert _pick_endpoint(eps)["url"] == "b"

    def test_empty_raises(self):
        import pytest
        with pytest.raises(RuntimeError):
            _pick_endpoint([])


class TestExtractMdFromResult:
    def test_direct_match(self):
        result = {"results": {"test": {"md_content": "# Hello"}}}
        assert _extract_md_from_result(result, "test.pdf") == "# Hello"

    def test_fallback_scan(self):
        result = {"results": {"other": {"md_content": "fallback"}}}
        assert _extract_md_from_result(result, "missing.pdf") == "fallback"

    def test_empty(self):
        assert _extract_md_from_result({}, "x.pdf") == ""
