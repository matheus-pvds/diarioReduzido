# diárioReduzido — Enhanced Municipal Gazette Summarizer

A feature-enhanced fork of `Diario_reduzido`. Adds **user authentication** (Werkzeug hashed passwords, session-based login) and **Flask-WTF forms** for secure access to municipal gazette AI summaries from **Governador Valadares (MG, Brazil)**.

## Features (inherits all from Diario_reduzido)

- Automatic gazette PDF scraping from transparency portal
- 6-model Gemini AI failover chain for summarization
- Serverless periodic check pattern
- Newspaper-themed UI with Markdown rendering

### Additional Features

- **User Authentication** — password-protected access with Werkzeug hashing
- **Login/Logout** — session-based authentication
- **Default Admin User** — auto-creates `admin/admin123` on first run
- **Post History** — authenticated users can view all previous posts (not just latest)
- **WTForms Login** — validated login form with CSRF protection and flash messages
- **URL-based Post Selection** — `?id=N` query parameter for historical posts

## Tech Stack

Python, Flask, Flask-SQLAlchemy, Flask-WTF, Google Gemini API, BeautifulSoup 4, Requests, Gunicorn, PostgreSQL, Vercel serverless, Werkzeug, ZoneInfo

## Architecture

```
app.py           → Flask app with routes, DB models, auth, scraping & update logic
processor.py     → GeminiClient with model failover chain
forms.py         → LoginForm (WTForms)
templates/
  index.html     → Newspaper-styled template with conditional auth UI
scrape_historico.py → Historical data scraping tool
```

### Database Models

- **Post** — content, model_used, pdf_link, date
- **AppConfig** — key-value config store
- **User** — username, password_hash (with `set_password`/`check_password` methods)

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Requires `GEMINI_API_KEY` environment variable.

## Deployment

`vercel.json` configured for Vercel serverless.
