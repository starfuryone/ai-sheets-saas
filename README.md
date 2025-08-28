# AI Sheets SaaS — Python Blueprint

This ZIP contains a clean blueprint aligned with a FastAPI + PostgreSQL + Alembic setup.
- Start the API: `uvicorn app.main:app --reload --port 8080`
- Run DB migrations: `alembic upgrade head`
- Docker dev stack: `docker-compose up --build`

**Note:** Secrets are placeholders. Update `.env` and Stripe/OpenAI keys before production.
