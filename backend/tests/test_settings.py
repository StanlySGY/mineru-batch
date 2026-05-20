from models import AppSetting


def _settings_payload(api_key="secret"):
    return {
        "defaults": {"timeout": 900, "outputFormat": "md", "startPageId": 0, "endPageId": 10},
        "mineruEndpoints": [{
            "url": "http://localhost:8086/file_parse",
            "backend": "hybrid-http-client",
            "serverUrl": "http://localhost:6002/v1",
            "enabled": True,
            "apiKey": api_key,
        }],
    }


class TestSettings:
    def test_put_and_get_masks_api_key(self, client):
        resp = client.put("/api/settings", json=_settings_payload())
        assert resp.status_code == 200
        endpoint = resp.json()["mineruEndpoints"][0]
        assert endpoint["hasApiKey"] is True
        assert "apiKey" not in endpoint

        resp = client.get("/api/settings")
        endpoint = resp.json()["mineruEndpoints"][0]
        assert endpoint["hasApiKey"] is True
        assert "apiKey" not in endpoint

    def test_empty_api_key_preserves_existing(self, client, db_session):
        client.put("/api/settings", json=_settings_payload("secret-1"))
        payload = _settings_payload("")
        resp = client.put("/api/settings", json=payload)
        assert resp.status_code == 200

        row = db_session.query(AppSetting).first()
        assert "secret-1" in row.value_json

    def test_invalid_endpoint_rejected(self, client):
        payload = _settings_payload()
        payload["mineruEndpoints"][0]["url"] = "ftp://example.com/file_parse"
        resp = client.put("/api/settings", json=payload)
        assert resp.status_code == 400
