# Werkstatt Zeiterfassung

Einfache Zeiterfassung für Werkstatt-Mitarbeiter mit Admin-Bereich.

- **Mitarbeiter** loggen sich mit Name + PIN ein und tragen ihre Arbeitszeit inkl.
  erledigter Aufgabe ein. Erlaubt sind Einträge von **2 Tagen rückwirkend bis
  1 Tag im Voraus** (`util.py`, `DAYS_BACK` / `DAYS_FORWARD`).
- **Admin** (`/admin`) verwaltet Mitarbeiter, verteilt Aufgaben mit Zeitraum,
  sieht/druckt die Zeitenliste und kann Firmenname + Admin-Passwort ändern.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env ausfüllen: ADMIN_PASSWORD und SECRET_KEY setzen
```

`SECRET_KEY` generieren:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Starten

```bash
.venv/bin/python app.py
```

Läuft standardmäßig auf `http://127.0.0.1:8090`. Beim ersten Start wird die
SQLite-Datenbank unter `instance/werkstatt.db` angelegt und der Admin-Account
aus `ADMIN_USERNAME` / `ADMIN_PASSWORD` gesetzt.

**Wichtig:** Nie mit `--host 0.0.0.0` starten (der Mac hat eine öffentliche IP).
Für den Zugriff aus dem Werkstatt-Netz per Tailscale, sonst auf `127.0.0.1` lassen.

## Bedienung

1. Als Admin unter `/admin` einloggen, Mitarbeiter anlegen (Name + PIN).
2. Optional Aufgaben mit Zeitraum anlegen und einem Mitarbeiter zuweisen
   (oder "Alle Mitarbeiter" für offene Aufgaben ohne festen Empfänger).
3. Mitarbeiter loggen sich unter `/` mit Name + PIN ein und tragen ihre Zeit ein.
4. Unter `/admin/zeiten` die Liste filtern (Mitarbeiter, Zeitraum) und über den
   "Drucken"-Button ausdrucken (Browser-Druckdialog, eigenes Druck-Stylesheet
   blendet Navigation/Filter aus).

## Deployment / Hosting später

Aktuell für den lokalen Testbetrieb ausgelegt (SQLite-Datei, Flask-Devserver).
Für echten Zugriff von unterwegs später:

- Produktions-WSGI-Server (z. B. `gunicorn`) statt `app.run(...)`.
- Hosting mit **persistentem** Speicher für `instance/werkstatt.db`
  (z. B. Render/Fly.io mit Volume) – ohne Volume geht die SQLite-Datei bei
  jedem Deploy verloren. Bei mehr als einer Handvoll Mitarbeitern lohnt sich
  ggf. der Wechsel auf Postgres.
- `SECRET_KEY` und `ADMIN_PASSWORD` als Umgebungsvariablen beim Hoster setzen,
  nicht im Repo.
