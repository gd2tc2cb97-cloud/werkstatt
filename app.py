import os
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
import util

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app.teardown_appcontext(db.close_db)


@app.context_processor
def inject_settings():
    settings = db.get_settings(db.get_db())
    return {"settings": settings}


def employee_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("employee_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def current_employee():
    if "employee_id" not in session:
        return None
    return db.get_employee(db.get_db(), session["employee_id"])


@app.route("/")
def index():
    if session.get("employee_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    dbc = db.get_db()
    employees = db.list_employees(dbc, active_only=True)

    if request.method == "POST":
        employee_id = request.form.get("employee_id", "")
        pin = request.form.get("pin", "")
        employee = db.get_employee(dbc, employee_id) if employee_id else None

        if not employee or not employee["active"]:
            flash("Bitte Mitarbeiter auswählen.", "error")
        elif not check_password_hash(employee["pin_hash"], pin):
            flash("PIN ist falsch.", "error")
        else:
            session.clear()
            session["employee_id"] = employee["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))

    return render_template("login.html", employees=employees)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET"])
@employee_required
def dashboard():
    dbc = db.get_db()
    employee = current_employee()
    range_start, range_end = util.allowed_entry_range()
    range_start_s, range_end_s = range_start.isoformat(), range_end.isoformat()

    day_entries = db.list_day_entries_for_employee(dbc, employee["id"], date_from=range_start_s, date_to=range_end_s)
    task_entries = db.list_task_entries_for_employee(dbc, employee["id"], date_from=range_start_s, date_to=range_end_s)

    older_cutoff = range_start_s
    day_history = [e for e in db.list_day_entries_for_employee(dbc, employee["id"]) if e["entry_date"] < older_cutoff][:14]

    tasks = db.list_tasks(dbc, employee_id=employee["id"], status="offen")
    tasks = [
        t for t in tasks
        if t["start_date"] <= range_end_s and t["end_date"] >= range_start_s
    ]

    return render_template(
        "dashboard.html",
        employee=employee,
        day_entries=day_entries,
        day_history=day_history,
        task_entries=task_entries,
        tasks=tasks,
        range_start=range_start,
        range_end=range_end,
        today=date.today(),
        util=util,
    )


@app.route("/tag/speichern", methods=["POST"])
@employee_required
def save_day_entry():
    dbc = db.get_db()
    employee = current_employee()

    entry_date = request.form.get("entry_date", "")
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    break_minutes = request.form.get("break_minutes") or 0

    if not util.date_in_allowed_range(entry_date):
        flash("Dieses Datum liegt außerhalb des erlaubten Zeitraums (2 Tage zurück, 1 Tag voraus).", "error")
        return redirect(url_for("dashboard"))

    if not start_time or not end_time:
        flash("Bitte Beginn und Ende der Arbeitszeit angeben.", "error")
        return redirect(url_for("dashboard"))

    try:
        break_minutes = int(break_minutes)
    except ValueError:
        break_minutes = 0

    existing = db.get_day_entry(dbc, employee["id"], entry_date)
    if existing and not util.date_in_allowed_range(existing["entry_date"]):
        flash("Dieser Tag kann nicht mehr bearbeitet werden.", "error")
        return redirect(url_for("dashboard"))

    db.upsert_day_entry(dbc, employee["id"], entry_date, start_time, end_time, break_minutes)
    flash("Tagesarbeitszeit gespeichert.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tag/<int:day_entry_id>/loeschen", methods=["POST"])
@employee_required
def delete_day_entry(day_entry_id):
    dbc = db.get_db()
    employee = current_employee()
    existing = db.get_day_entry_by_id(dbc, day_entry_id)
    if not existing or existing["employee_id"] != employee["id"]:
        flash("Eintrag nicht gefunden.", "error")
    elif not util.date_in_allowed_range(existing["entry_date"]):
        flash("Dieser Eintrag kann nicht mehr gelöscht werden.", "error")
    else:
        db.delete_day_entry(dbc, day_entry_id)
        flash("Tagesarbeitszeit gelöscht.", "success")
    return redirect(url_for("dashboard"))


@app.route("/aufgabenzeit/speichern", methods=["POST"])
@employee_required
def save_task_entry():
    dbc = db.get_db()
    employee = current_employee()

    entry_id = request.form.get("entry_id") or None
    entry_date = request.form.get("entry_date", "")
    task_id = request.form.get("task_id") or None
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    notes = request.form.get("notes", "").strip()

    if not util.date_in_allowed_range(entry_date):
        flash("Dieses Datum liegt außerhalb des erlaubten Zeitraums (2 Tage zurück, 1 Tag voraus).", "error")
        return redirect(url_for("dashboard"))

    if not start_time or not end_time:
        flash("Bitte Beginn und Ende angeben.", "error")
        return redirect(url_for("dashboard"))

    if not notes:
        flash("Bitte kurz beschreiben, was erledigt wurde.", "error")
        return redirect(url_for("dashboard"))

    if entry_id:
        existing = db.get_task_entry(dbc, entry_id)
        if not existing or existing["employee_id"] != employee["id"]:
            flash("Eintrag nicht gefunden.", "error")
            return redirect(url_for("dashboard"))
        if not util.date_in_allowed_range(existing["entry_date"]):
            flash("Dieser Eintrag kann nicht mehr bearbeitet werden.", "error")
            return redirect(url_for("dashboard"))
        db.update_task_entry(dbc, entry_id, entry_date, task_id, start_time, end_time, notes)
        flash("Aufgabenzeit aktualisiert.", "success")
    else:
        db.create_task_entry(dbc, employee["id"], entry_date, task_id, start_time, end_time, notes)
        flash("Aufgabenzeit gespeichert.", "success")

    return redirect(url_for("dashboard"))


@app.route("/aufgabenzeit/<int:entry_id>/loeschen", methods=["POST"])
@employee_required
def delete_task_entry(entry_id):
    dbc = db.get_db()
    employee = current_employee()
    existing = db.get_task_entry(dbc, entry_id)
    if not existing or existing["employee_id"] != employee["id"]:
        flash("Eintrag nicht gefunden.", "error")
    elif not util.date_in_allowed_range(existing["entry_date"]):
        flash("Dieser Eintrag kann nicht mehr gelöscht werden.", "error")
    else:
        db.delete_task_entry(dbc, entry_id)
        flash("Aufgabenzeit gelöscht.", "success")
    return redirect(url_for("dashboard"))


from admin import bp as admin_bp  # noqa: E402

app.register_blueprint(admin_bp)
db.init_db(admin_username=ADMIN_USERNAME, admin_password=ADMIN_PASSWORD)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8090)))
    args = p.parse_args()
    if args.host in ("0.0.0.0", "::"):
        raise SystemExit(
            "Nicht auf alle Schnittstellen binden – der Mac hat eine öffentliche IP. "
            "Für den Live-Betrieb auf einem Server hinter HTTPS-Proxy deployen."
        )
    app.run(host=args.host, port=args.port, debug=os.environ.get("FLASK_DEBUG") == "1")
