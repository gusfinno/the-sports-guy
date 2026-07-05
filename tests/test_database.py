import datetime
import sqlite3

import pytest

import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_NAME", str(db_path))
    database.init_db()
    return db_path


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def test_init_db_creates_tables(db):
    conn = _connect(db)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"f1_races", "drivers", "results", "constructors"} <= names

def test_schedule_exists_for_year(db):
    assert not database.schedule_exists_for_year(2026)
    database.add_schedule_to_db(20261, 2026, "Bahrain: Sakhir", False, 3, 2)
    assert database.schedule_exists_for_year(2026)
    assert not database.schedule_exists_for_year(2025)


def test_get_races_returns_past_races_and_next(db):
    database.add_schedule_to_db(20261, 2026, "Bahrain: Sakhir", False, 3, 2)
    database.add_schedule_to_db(20262, 2026, "Saudi: Jeddah", False, 3, 9)
    database.add_schedule_to_db(20263, 2026, "Australia: Melbourne", False, 12, 1)

    races = database.get_races(datetime.date(2026, 6, 1))

    assert [r.round for r in races] == [1, 2, 3]
    assert races[-2].round == 2


def test_get_races_raises_when_no_past_races(db):
    database.add_schedule_to_db(20261, 2026, "Australia: Melbourne", False, 12, 1)
    with pytest.raises(ValueError):
        database.get_races(datetime.date(2026, 6, 1))


def test_get_races_excludes_other_years(db):
    database.add_schedule_to_db(20251, 2025, "Old: Race", False, 6, 1) 
    database.add_schedule_to_db(202611, 2026, "Bahrain: Sakhir", False, 3, 2)

    races = database.get_races(datetime.date(2026, 6, 1))

    assert all(r.year == 2026 for r in races)


def test_constructor_add_and_lookup_by_name(db):
    assert not database.constructors_exist()
    database.add_constructor_to_db("Ferrari", "Italian")
    assert database.constructors_exist()

    cid = database.get_constructor_id("Ferrari")
    assert cid > 0
    assert database.get_constructor_id("Nonexistent Team") == 0

def test_driver_add_lookup_and_type_dispatch(db):
    database.add_constructor_to_db("Ferrari", "Italian")
    cid = database.get_constructor_id("Ferrari")

    assert not database.drivers_exist()
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "http://img/lec", 100.0, "Monegasque")
    assert database.drivers_exist()

    d = database.get_driver(16)
    assert d is not None
    assert d.last_name == "Leclerc"
    assert d.nationality == "Monegasque"
    assert d.constructor_id == cid

    assert database.get_constructor_id(16) == cid

    assert database.get_driver(999) is None


def test_two_drivers_fill_both_constructor_slots(db):
    database.add_constructor_to_db("Ferrari", "Italian")
    cid = database.get_constructor_id("Ferrari")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "u", 100.0, "Monegasque")
    database.add_drivers_to_db(44, "HAM", "Lewis", "Hamilton", "Ferrari", "u", 90.0, "British")

    conn = _connect(db)
    d1, d2 = conn.execute(
        "SELECT driver_1_id, driver_2_id FROM constructors WHERE id = ?", (cid,)
    ).fetchone()
    conn.close()
    assert {d1, d2} == {16, 44}


def test_adding_same_driver_twice_is_idempotent(db):
    database.add_constructor_to_db("Ferrari", "Italian")
    cid = database.get_constructor_id("Ferrari")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "u", 100.0, "Monegasque")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "u", 100.0, "Monegasque")

    conn = _connect(db)
    d1, d2 = conn.execute(
        "SELECT driver_1_id, driver_2_id FROM constructors WHERE id = ?", (cid,)
    ).fetchone()
    conn.close()
    assert d1 == 16
    assert d2 is None


def test_clear_drivers(db):
    database.add_constructor_to_db("Ferrari", "Italian")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "u", 100.0, "Monegasque")
    assert database.drivers_exist()
    database.clear_drivers()
    assert not database.drivers_exist()


def test_results_flow(db):
    database.add_constructor_to_db("Ferrari", "Italian")
    cid = database.get_constructor_id("Ferrari")
    database.add_drivers_to_db(16, "LEC", "Charles", "Leclerc", "Ferrari", "http://img", 100.0, "Monegasque")

    assert not database.results_exist_for_round(1)
    stints = [database.Stint(tire="SOFT", laps=20), database.Stint(tire="HARD", laps=30)]
    database.add_race_to_db(1, 16, cid, 3, 1, stints, 2, 50, "Finished")
    assert database.results_exist_for_round(1)

    results = database.get_basic_results(1)
    assert len(results) == 1
    r = results[0]
    assert r.driver_id == 16
    assert r.constructor_name == "Ferrari"
    assert r.position == 1
    assert [s.tire for s in r.stints] == ["SOFT", "HARD"]

    database.clear_results_for_round(1)
    assert not database.results_exist_for_round(1)
