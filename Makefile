install:
	pip install -r requirements.txt
dev:
	uvicorn app.main:app --reload