from datetime import UTC, datetime, timedelta

from models import FileTask, OutputFormat, TaskStatus


class TestQualityReport:
    def test_empty_report(self, client):
        resp = client.get("/api/reports/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["success_rate"] == 0
        assert data["recent_failures"] == []

    def test_report_counts_and_failures(self, client, db_session):
        now = datetime.now(UTC)
        done = FileTask(
            original_filename="ok.pdf",
            saved_filename="ok.pdf",
            file_path="/tmp/ok.pdf",
            file_size=1,
            status=TaskStatus.COMPLETED,
            output_format=OutputFormat.MD,
            started_at=now - timedelta(seconds=2),
            completed_at=now,
        )
        failed = FileTask(
            original_filename="bad.pdf",
            saved_filename="bad.pdf",
            file_path="/tmp/bad.pdf",
            file_size=1,
            status=TaskStatus.FAILED,
            output_format=OutputFormat.MD,
            error_message="boom",
            completed_at=now,
        )
        db_session.add_all([done, failed])
        db_session.commit()

        data = client.get("/api/reports/quality").json()
        assert data["total"] == 2
        assert data["completed"] == 1
        assert data["failed"] == 1
        assert data["success_rate"] == 50.0
        assert data["recent_failures"][0]["filename"] == "bad.pdf"
