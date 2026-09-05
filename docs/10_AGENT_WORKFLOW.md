# Antigravity Agent Workflow

## Before Coding

1.  Inspect repository.
2.  Read `AGENTS.md`.
3.  Read all relevant `docs/` files.
4.  Identify existing code before creating files.
5.  Check current migrations.
6.  Check current environment configuration.
7.  Preserve working code.

## During Coding

For each feature:

### Step 1

Create/update models.

### Step 2

Create migration.

### Step 3

Implement business logic.

### Step 4

Implement permissions.

### Step 5

Implement URL.

### Step 6

Implement view.

### Step 7

Implement template.

### Step 8

Connect reusable components.

### Step 9

Add tests.

### Step 10

Run checks.

## Commands

Use the project's actual environment, but typically:

``` bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test
```

If Tailwind/build tooling exists, run its documented build command.

## Git

Use meaningful commits, for example:

``` text
feat(tasks): add task management
feat(bugs): add bug workflow
feat(chat): add workspace channels
fix(auth): enforce workspace permission
test(tasks): add task permission coverage
```

Do not commit: - `.env` - secrets - generated caches - local database
files when PostgreSQL is the intended deployment database

## If Something Is Unclear

Prefer the existing blueprint.

If two documents conflict: 1. `AGENTS.md` 2.
`docs/00_PROJECT_BLUEPRINT.md` 3. feature-specific documentation 4.
existing tested code

Do not silently change product requirements.

## Completion Report

After each major phase, report: - files changed - features completed -
tests run - known limitations - next recommended phase

The agent should continue implementation rather than stopping after
creating a plan.
