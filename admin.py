from datetime import date, timedelta
from functools import wraps

from flask import (Blueprint, flash, redirect, render_template, request,
                    session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import util

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        dbc = db.get_db()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = db.get_admin_by_username(dbc, username)
        if not admin or not check_password_hash(admin["password_hash"], password):
            flash("Benutzername oder Passwort ist falsch.", "error")
        else:
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def dashboard():
    dbc = db.get_db()
    employees = db.list_employees(dbc, active_only=True)

    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    week_entries = db.list_entries(dbc, date_from=week_start)

    hours_by_employee = {}
    for e in week_entries:
        minutes = util.compute_minutes(e["start_time"], e["end_time"], e["break_minutes"])
        hours_by_employee[e["employee_name"]] = hours_by_employee.get(e["employee_name"], 0) + minutes

    open_tasks = db.list_tasks(dbc, status="offen")

    return render_template(
        "admin/dashboard.html",
        employees=employees,
        hours_by_employee={name: util.format_hours(m) for name, m in hours_by_employee.items()},
        open_tasks=open_tasks,
        week_start=week_start,
    )


# ---------- Mitarbeiter ----------

@bp.route("/mitarbeiter")
@admin_required
def employees():
    dbc = db.get_db()
    return render_template("admin/employees.html", employees=db.list_employees(dbc))


@bp.route("/mitarbeiter/neu", methods=["GET", "POST"])
@admin_required
def employee_new():
    if request.method == "POST":
        dbc = db.get_db()
        name = request.form.get("name", "").strip()
        pin = request.form.get("pin", "").strip()
        if not name or not pin:
            flash("Name und PIN sind erforderlich.", "error")
        elif db.get_employee_by_name(dbc, name):
            flash("Ein Mitarbeiter mit diesem Namen existiert bereits.", "error")
        else:
            db.create_employee(dbc, name, pin)
            flash(f"Mitarbeiter „{name}“ angelegt.", "success")
            return redirect(url_for("admin.employees"))
    return render_template("admin/employee_form.html", employee=None)


@bp.route("/mitarbeiter/<int:employee_id>/bearbeiten", methods=["GET", "POST"])
@admin_required
def employee_edit(employee_id):
    dbc = db.get_db()
    employee = db.get_employee(dbc, employee_id)
    if not employee:
        flash("Mitarbeiter nicht gefunden.", "error")
        return redirect(url_for("admin.employees"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        active = bool(request.form.get("active"))
        new_pin = request.form.get("pin", "").strip()
        if not name:
            flash("Name ist erforderlich.", "error")
        else:
            db.update_employee(dbc, employee_id, name, active)
            if new_pin:
                db.set_employee_pin(dbc, employee_id, new_pin)
            flash("Mitarbeiter aktualisiert.", "success")
            return redirect(url_for("admin.employees"))

    return render_template("admin/employee_form.html", employee=employee)


# ---------- Aufgaben ----------

@bp.route("/aufgaben")
@admin_required
def tasks():
    dbc = db.get_db()
    return render_template(
        "admin/tasks.html",
        tasks=db.list_tasks(dbc),
        employees=db.list_employees(dbc, active_only=True),
    )


@bp.route("/aufgaben/neu", methods=["GET", "POST"])
@admin_required
def task_new():
    dbc = db.get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        employee_id = request.form.get("employee_id") or None
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")

        if not title or not start_date or not end_date:
            flash("Titel, Start- und Enddatum sind erforderlich.", "error")
        elif end_date < start_date:
            flash("Das Enddatum darf nicht vor dem Startdatum liegen.", "error")
        else:
            db.create_task(dbc, title, description, employee_id, start_date, end_date)
            flash("Aufgabe angelegt.", "success")
            return redirect(url_for("admin.tasks"))

    return render_template(
        "admin/task_form.html", task=None,
        employees=db.list_employees(dbc, active_only=True),
    )


@bp.route("/aufgaben/<int:task_id>/bearbeiten", methods=["GET", "POST"])
@admin_required
def task_edit(task_id):
    dbc = db.get_db()
    task = db.get_task(dbc, task_id)
    if not task:
        flash("Aufgabe nicht gefunden.", "error")
        return redirect(url_for("admin.tasks"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        employee_id = request.form.get("employee_id") or None
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        status = request.form.get("status", "offen")

        if not title or not start_date or not end_date:
            flash("Titel, Start- und Enddatum sind erforderlich.", "error")
        elif end_date < start_date:
            flash("Das Enddatum darf nicht vor dem Startdatum liegen.", "error")
        else:
            db.update_task(dbc, task_id, title, description, employee_id, start_date, end_date, status)
            flash("Aufgabe aktualisiert.", "success")
            return redirect(url_for("admin.tasks"))

    return render_template(
        "admin/task_form.html", task=task,
        employees=db.list_employees(dbc, active_only=True),
    )


@bp.route("/aufgaben/<int:task_id>/loeschen", methods=["POST"])
@admin_required
def task_delete(task_id):
    dbc = db.get_db()
    db.delete_task(dbc, task_id)
    flash("Aufgabe gelöscht.", "success")
    return redirect(url_for("admin.tasks"))


# ---------- Zeiten (Liste + Druckansicht) ----------

@bp.route("/zeiten")
@admin_required
def entries():
    dbc = db.get_db()
    employee_id = request.args.get("employee_id") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None

    rows = db.list_entries(dbc, employee_id=employee_id, date_from=date_from, date_to=date_to)

    total_minutes = 0
    sums_by_employee = {}
    entries_view = []
    for r in rows:
        minutes = util.compute_minutes(r["start_time"], r["end_time"], r["break_minutes"])
        total_minutes += minutes
        sums_by_employee[r["employee_name"]] = sums_by_employee.get(r["employee_name"], 0) + minutes
        entries_view.append({"row": r, "hours": util.format_hours(minutes)})

    return render_template(
        "admin/entries.html",
        entries=entries_view,
        employees=db.list_employees(dbc),
        selected_employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        total_hours=util.format_hours(total_minutes),
        sums_by_employee={name: util.format_hours(m) for name, m in sums_by_employee.items()},
    )


# ---------- Einstellungen ----------

@bp.route("/einstellungen", methods=["GET", "POST"])
@admin_required
def settings():
    dbc = db.get_db()
    if request.method == "POST":
        db.set_setting(dbc, "company_name", request.form.get("company_name", "").strip())

        new_password = request.form.get("new_password", "").strip()
        if new_password:
            db.set_admin_password(dbc, session["admin_id"], new_password)
            flash("Passwort geändert.", "success")

        flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html", settings=db.get_settings(dbc))
