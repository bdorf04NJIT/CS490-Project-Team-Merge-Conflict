# Frontend

Requires Node.js 22.12+ and npm.

Create `frontend/.env.local` with the values shared by the team:

```dotenv
VITE_SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_SUPABASE_PUBLISHABLE_KEY
```

From the project root, run in PowerShell:

```powershell
cd frontend
npm ci
npm run dev
```

Keep the [backend](../backend/README.md) running in another terminal. Open the URL printed by Vite (usually http://localhost:5173) and sign in or create an account.
