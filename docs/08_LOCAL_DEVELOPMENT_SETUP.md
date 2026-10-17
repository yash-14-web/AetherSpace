# AetherSpace Local Development Setup Guide

A complete, beginner-friendly, Windows-compatible guide for setting up and running AetherSpace locally.

---

## 1. Prerequisites & Required Tools

Ensure the following tools are installed on your workstation:

| Tool | Recommended Version | Verification Command | Notes |
|---|---|---|---|
| **Python** | 3.12.x or 3.13.x | `python --version` | Ensure "Add Python to PATH" was checked during install. |
| **Git** | 2.40+ | `git --version` | Standard version control. |
| **PostgreSQL** | 15+ (Local or Cloud) | `psql --version` | Or use a free Supabase Cloud project (`DATABASE_URL`). |
| **Node.js** | 20.x LTS | `node --version` | Required only if rebuilding Tailwind CSS or running Playwright E2E tests. |

---

## 2. Step-by-Step Installation

### Step 1: Open Terminal in Project Directory
On Windows, open PowerShell or Command Prompt in the repository folder:
```powershell
cd "c:\Data Science and Gen Ai projects\AetherSpace"
```

### Step 2: Create & Activate Python Virtual Environment
```powershell
# Create a virtual environment named .venv
python -m venv .venv

# Activate the virtual environment (PowerShell)
.venv\Scripts\Activate.ps1

# (If using standard Command Prompt cmd.exe)
# .venv\Scripts\activate.bat
```
*(If PowerShell blocks execution of scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and re-activate).*

### Step 3: Install Python Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Local Environment Variables
Create a local `.env` file by copying `.env.example`:
```powershell
Copy-Item .env.example .env
```
Open `.env` in your code editor and populate the required keys:
```ini
# Django Core Settings
DJANGO_SECRET_KEY=local-dev-secret-key-change-in-production
DJANGO_DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,.onrender.com

# Database Connection (Supabase PostgreSQL or Local Postgres)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-HOST]:5432/postgres

# Supabase Storage & Services (Optional for basic local UI testing)
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_placeholder
SUPABASE_SECRET_KEY=sb_secret_placeholder
SUPABASE_STORAGE_BUCKET=aetherspace-storage
```

> [!IMPORTANT]
> Never commit your `.env` file to Git. It is already included in `.gitignore`.

### Step 5: Run Database Migrations
Apply all database migrations to initialize tables and relationships:
```powershell
python manage.py migrate
```

### Step 6: Create an Administrator Account
Run Django's superuser creation command:
```powershell
python manage.py createsuperuser
```
Follow the prompts to enter your email and password.
*(Note: Superuser accounts automatically receive `approval_status = APPROVED` and `role = ADMIN`, allowing immediate login).*

### Step 7: Collect Static Assets (WhiteNoise)
```powershell
python manage.py collectstatic --noinput
```

---

## 3. Running the Development Server

### Standard Development Server (HTTP + Synchronous)
```powershell
python manage.py runserver 127.0.0.1:8000
```

### Asynchronous ASGI Server (Daphne with WebSockets Enabled)
To test real-time Chat and Meet Hub WebSockets locally:
```powershell
daphne -b 127.0.0.1 -p 8000 aetherspace.asgi:application
```

Open your browser and navigate to:
**`http://127.0.0.1:8000/auth/login/`**

Log in using your superuser email or generated Contributor ID.

---

## 4. Running the Automated Test Suite

AetherSpace includes automated unit and integration tests across all modules.

### Run Django System Checks
```powershell
python manage.py check
```
*(Expected output: `System check identified no issues (0 silenced).`)*

### Run All Backend Tests
```powershell
python manage.py test
```

### Run Tests for Specific Modules
```powershell
# Test Meetings & Call Sessions
python manage.py test meetings

# Test WebSockets & Signaling
python manage.py test tests.test_meeting_webrtc_signaling

# Test Workspaces & RBAC
python manage.py test workspaces

# Test Tasks & Defect Triage
python manage.py test tasks bugs
```

---

## 5. Common Local Setup Failures & Troubleshooting

### Error: `django.db.utils.OperationalError: could not connect to server`
* **Cause**: `DATABASE_URL` in `.env` is invalid, network connection to Supabase is offline, or PgBouncer timed out.
* **Resolution**:
  1. Check internet connectivity.
  2. Verify your Supabase PostgreSQL password in `.env`.
  3. Ensure port `5432` or transaction pooler port `6543` is reachable.

### Error: `ModuleNotFoundError: No module named 'daphne'`
* **Cause**: Virtual environment is not activated or `requirements.txt` was not installed.
* **Resolution**: Run `.venv\Scripts\Activate.ps1` followed by `pip install -r requirements.txt`.

### Error: `psycopg2.errors.UndefinedTable: relation ... does not exist`
* **Cause**: Migrations have not been applied to the target database.
* **Resolution**: Run `python manage.py migrate`.
