import datetime as dt

import pytest
from fastapi.testclient import TestClient

import database
import main


class _FixedDateTime:
    @classmethod
    def now(cls):
        return dt.datetime(2026, 6, 1)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_NAME", str(db_path))
    monkeypatch.setattr(main, "load_schedule_data", lambda: None)
    with TestClient(main.app) as c:
        yield c


def test_home_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "THESPORTSGUY" in resp.text


def test_f1_renders_seeded_results(client, monkeypatch):
    monkeypatch.setattr(main, "load_constructor_data", lambda: None)
    monkeypatch.setattr(main, "load_driver_data", lambda *a, **k: None)
    monkeypatch.setattr(main, "load_race_data", lambda *a, **k: None)
    monkeypatch.setattr(main, "datetime", _FixedDateTime)

    database.add_schedule_to_db(20261, 2026, "Bahrain: Sakhir", False, 1, 1)
    database.add_schedule_to_db(20262, 2026, "Saudi: Jeddah", False, 12, 1)
    database.add_constructor_to_db("Ferrari", "Italian")
    cid = database.get_constructor_id("Ferrari")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "http://img", "Monegasque")
    database.add_race_to_db(
        20261, 16, cid, 3, 1, [database.Stint(tire="SOFT", laps=50)], 2, 50, "Finished",
        "1:32:45.123", 1
    )

    resp = client.get("/f1")
    assert resp.status_code == 200
    assert "Bahrain: Sakhir" in resp.text
    assert "Leclerc" in resp.text
