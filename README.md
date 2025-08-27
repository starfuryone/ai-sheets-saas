# 🧠 Claude-SaaS: AI Sheets Backend

Claude-SaaS is a production-ready, FastAPI-powered backend that integrates powerful AI functions into **Google Sheets** via custom formulas like:

- `=GPT_CLEAN(text)`
- `=GPT_SEO(text)`
- `=GPT_SUMMARIZE(range)`

🔗 [Frontend Integration: Google Apps Script](google-apps-script/)

---

## 🚀 Features

- ✅ **FastAPI Backend** — Built with async, typed endpoints
- ✅ **AI Functions** — Clean, summarize, enrich SEO via OpenAI/Claude
- ✅ **Credit System** — Deduct credits per function call
- ✅ **Stripe Integration** — Credit packs and webhook fulfillment
- ✅ **Magic Link Authentication** — Passwordless login via email
- ✅ **PostgreSQL + Redis** — Robust, scalable architecture
- ✅ **Google Sheets Sidebar UI** — Live balance display

---

## 🧱 Directory Structure

```
saas-sheets-ai/
├── app/                 # FastAPI app code
├── scripts/             # Utilities and DB seeding
├── tests/               # Unit + integration tests
├── alembic/             # Database migration system
├── google-apps-script/  # Google Sheets frontend
├── Dockerfile           # Container config
├── docker-compose.yml   # Local dev orchestration
├── requirements.txt     # Python dependencies
└── README.md
```

---

## ⚙️ Quickstart

1. **Clone the repo**

```bash
git clone https://github.com/starfuryone/ai-sheets-saas.git
cd ai-sheets-saas
```

2. **Create `.env` from template**

```bash
cp .env.example .env
```

3. **Run locally with Docker**

```bash
docker-compose up --build
```

4. **Visit the API**

```
http://localhost:8000/docs
```

5. **Test it**

```bash
pytest tests/
```

---

## ✨ Credit Pack Flow

1. User opens Google Sheet
2. Calls a custom formula (e.g., `=GPT_CLEAN(A2)`)
3. Google Apps Script sends request to FastAPI backend
4. Backend verifies JWT / credits → deducts balance → calls AI
5. Result is returned to sheet and balance is updated live

---

## 🧪 Tests

```bash
pytest tests/
```

---

## 📜 License

MIT — free to use, fork, and modify.

---

> Built with ❤️ by [@starfuryone](https://github.com/starfuryone)
