"""Datenbank: Mitarbeiter, Tagesarbeitszeiten, Aufgabenzeiten, Aufgaben, Admins, Einstellungen."""

import sqlite3
from pathlib import Path

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = INSTANCE_DIR / "werkstatt.db"

DEFAULT_SETTINGS = {
    "company_name": "Meine Werkstatt",
}


def connect():
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(admin_username=None, admin_password=None):
    db = connect()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employees (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            pin_hash   TEXT NOT NULL,
            active     INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admins (
            id            INTEGER PRIMARY KEY,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );

        -- Aufgabe: z.B. "Bremsen prüfen" für ein bestimmtes Fahrzeug (Kennzeichen),
        -- optional einem Mitarbeiter zugewiesen, mit vorgegebenem Zeitraum.
        CREATE TABLE IF NOT EXISTS tasks (
            id             INTEGER PRIMARY KEY,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            license_plate  TEXT NOT NULL DEFAULT '',
            employee_id    INTEGER REFERENCES employees(id),
            start_date     TEXT NOT NULL,
            end_date       TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'offen',
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Tagesarbeitszeit: Kommen/Gehen/Pause, ein Eintrag pro Mitarbeiter und Tag.
        CREATE TABLE IF NOT EXISTS day_entries (
            id            INTEGER PRIMARY KEY,
            employee_id   INTEGER NOT NULL REFERENCES employees(id),
            entry_date    TEXT NOT NULL,
            start_time    TEXT NOT NULL,
            end_time      TEXT NOT NULL,
            break_minutes INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(employee_id, entry_date)
        );

        -- Aufgabenzeit: einzelne Zeitblöcke, die einer Aufgabe zugeordnet sind
        -- (mehrere pro Tag möglich).
        CREATE TABLE IF NOT EXISTS task_entries (
            id          INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            entry_date  TEXT NOT NULL,
            task_id     INTEGER REFERENCES tasks(id),
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            notes       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_day_entries_employee_date
            ON day_entries(employee_id, entry_date);
        CREATE INDEX IF NOT EXISTS idx_task_entries_employee_date
            ON task_entries(employee_id, entry_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_employee
            ON tasks(employee_id, start_date, end_date);
    """)

    for key, value in DEFAULT_SETTINGS.items():
        db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    if admin_username and admin_password:
        existing = db.execute(
            "SELECT id FROM admins WHERE username = ?", (admin_username,)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (admin_username, generate_password_hash(admin_password, method="pbkdf2:sha256")),
            )

    db.close()


# ---------- Settings ----------

def get_settings(db):
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    settings.update({row["key"]: row["value"] for row in rows})
    return settings


def set_setting(db, key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ---------- Employees ----------

def list_employees(db, active_only=False):
    sql = "SELECT * FROM employees"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name COLLATE NOCASE"
    return db.execute(sql).fetchall()


def get_employee(db, employee_id):
    return db.execute(
        "SELECT * FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()


def get_employee_by_name(db, name):
    return db.execute(
        "SELECT * FROM employees WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()


def create_employee(db, name, pin):
    db.execute(
        "INSERT INTO employees (name, pin_hash) VALUES (?, ?)",
        (name, generate_password_hash(pin, method="pbkdf2:sha256")),
    )


def update_employee(db, employee_id, name, active):
    db.execute(
        "UPDATE employees SET name = ?, active = ? WHERE id = ?",
        (name, 1 if active else 0, employee_id),
    )


def set_employee_pin(db, employee_id, pin):
    db.execute(
        "UPDATE employees SET pin_hash = ? WHERE id = ?",
        (generate_password_hash(pin, method="pbkdf2:sha256"), employee_id),
    )


# ---------- Tasks ----------

def list_tasks(db, employee_id=None, status=None):
    sql = (
        "SELECT tasks.*, employees.name AS employee_name "
        "FROM tasks LEFT JOIN employees ON employees.id = tasks.employee_id "
        "WHERE 1=1"
    )
    params = []
    if employee_id is not None:
        sql += " AND (tasks.employee_id = ? OR tasks.employee_id IS NULL)"
        params.append(employee_id)
    if status:
        sql += " AND tasks.status = ?"
        params.append(status)
    sql += " ORDER BY tasks.start_date, tasks.id"
    return db.execute(sql, params).fetchall()


def get_task(db, task_id):
    return db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def create_task(db, title, description, license_plate, employee_id, start_date, end_date):
    db.execute(
        "INSERT INTO tasks (title, description, license_plate, employee_id, start_date, end_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, description, license_plate, employee_id, start_date, end_date),
    )


def update_task(db, task_id, title, description, license_plate, employee_id, start_date, end_date, status):
    db.execute(
        "UPDATE tasks SET title = ?, description = ?, license_plate = ?, employee_id = ?, "
        "start_date = ?, end_date = ?, status = ? WHERE id = ?",
        (title, description, license_plate, employee_id, start_date, end_date, status, task_id),
    )


def delete_task(db, task_id):
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


# ---------- Tagesarbeitszeit (day_entries) ----------

def get_day_entry(db, employee_id, entry_date):
    return db.execute(
        "SELECT * FROM day_entries WHERE employee_id = ? AND entry_date = ?",
        (employee_id, entry_date),
    ).fetchone()


def get_day_entry_by_id(db, day_entry_id):
    return db.execute(
        "SELECT * FROM day_entries WHERE id = ?", (day_entry_id,)
    ).fetchone()


def list_day_entries_for_employee(db, employee_id, date_from=None, date_to=None):
    sql = "SELECT * FROM day_entries WHERE employee_id = ?"
    params = [employee_id]
    if date_from:
        sql += " AND entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND entry_date <= ?"
        params.append(date_to)
    sql += " ORDER BY entry_date DESC"
    return db.execute(sql, params).fetchall()


def list_day_entries(db, employee_id=None, date_from=None, date_to=None):
    sql = (
        "SELECT day_entries.*, employees.name AS employee_name "
        "FROM day_entries JOIN employees ON employees.id = day_entries.employee_id "
        "WHERE 1=1"
    )
    params = []
    if employee_id:
        sql += " AND day_entries.employee_id = ?"
        params.append(employee_id)
    if date_from:
        sql += " AND day_entries.entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND day_entries.entry_date <= ?"
        params.append(date_to)
    sql += " ORDER BY day_entries.entry_date, employees.name COLLATE NOCASE"
    return db.execute(sql, params).fetchall()


def upsert_day_entry(db, employee_id, entry_date, start_time, end_time, break_minutes):
    db.execute(
        "INSERT INTO day_entries (employee_id, entry_date, start_time, end_time, break_minutes) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(employee_id, entry_date) DO UPDATE SET "
        "start_time = excluded.start_time, end_time = excluded.end_time, "
        "break_minutes = excluded.break_minutes, updated_at = datetime('now')",
        (employee_id, entry_date, start_time, end_time, break_minutes),
    )


def delete_day_entry(db, day_entry_id):
    db.execute("DELETE FROM day_entries WHERE id = ?", (day_entry_id,))


# ---------- Aufgabenzeiten (task_entries) ----------

def list_task_entries_for_employee(db, employee_id, date_from=None, date_to=None):
    sql = (
        "SELECT task_entries.*, tasks.title AS task_title, tasks.license_plate AS task_license_plate "
        "FROM task_entries LEFT JOIN tasks ON tasks.id = task_entries.task_id "
        "WHERE task_entries.employee_id = ?"
    )
    params = [employee_id]
    if date_from:
        sql += " AND task_entries.entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND task_entries.entry_date <= ?"
        params.append(date_to)
    sql += " ORDER BY task_entries.entry_date DESC, task_entries.start_time DESC"
    return db.execute(sql, params).fetchall()


def list_task_entries(db, employee_id=None, date_from=None, date_to=None):
    sql = (
        "SELECT task_entries.*, employees.name AS employee_name, "
        "tasks.title AS task_title, tasks.license_plate AS task_license_plate "
        "FROM task_entries "
        "JOIN employees ON employees.id = task_entries.employee_id "
        "LEFT JOIN tasks ON tasks.id = task_entries.task_id "
        "WHERE 1=1"
    )
    params = []
    if employee_id:
        sql += " AND task_entries.employee_id = ?"
        params.append(employee_id)
    if date_from:
        sql += " AND task_entries.entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND task_entries.entry_date <= ?"
        params.append(date_to)
    sql += " ORDER BY task_entries.entry_date, employees.name COLLATE NOCASE, task_entries.start_time"
    return db.execute(sql, params).fetchall()


def get_task_entry(db, entry_id):
    return db.execute(
        "SELECT * FROM task_entries WHERE id = ?", (entry_id,)
    ).fetchone()


def create_task_entry(db, employee_id, entry_date, task_id, start_time, end_time, notes):
    db.execute(
        "INSERT INTO task_entries (employee_id, entry_date, task_id, start_time, end_time, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (employee_id, entry_date, task_id, start_time, end_time, notes),
    )


def update_task_entry(db, entry_id, entry_date, task_id, start_time, end_time, notes):
    db.execute(
        "UPDATE task_entries SET entry_date = ?, task_id = ?, start_time = ?, end_time = ?, "
        "notes = ?, updated_at = datetime('now') WHERE id = ?",
        (entry_date, task_id, start_time, end_time, notes, entry_id),
    )


def delete_task_entry(db, entry_id):
    db.execute("DELETE FROM task_entries WHERE id = ?", (entry_id,))


# ---------- Admins ----------

def get_admin_by_username(db, username):
    return db.execute(
        "SELECT * FROM admins WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()


def set_admin_password(db, admin_id, password):
    db.execute(
        "UPDATE admins SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password, method="pbkdf2:sha256"), admin_id),
    )
