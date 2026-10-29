# Backend

Requires Python 3.12+.

Create `backend/.env` with the development values shared privately by the team:

```dotenv
SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL
DATABASE_URL=YOUR_POSTGRES_CONNECTION_STRING
```

The database URL must start with `postgresql+psycopg://` and include `sslmode=require`. Do not commit `.env`.

From the project root, run in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app run --debug
```

Keep this terminal running at http://127.0.0.1:5000. Start the [frontend](../frontend/README.md) in another terminal.
