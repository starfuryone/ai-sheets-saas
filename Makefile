.PHONY: run dev fmt lint test migrate

    run:
	uvicorn app.main:app --reload --port 8080

    dev: run

    fmt:
	ruff format .

    lint:
	ruff check . || true

    test:
	pytest -q

    migrate:
	alembic upgrade head
