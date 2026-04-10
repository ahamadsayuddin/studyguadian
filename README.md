# Emotion-Aware Study Assistant

A Python full-stack web application built with Django, PostgreSQL, OpenCV, and DeepFace. It includes a premium dashboard UI, webcam emotion analysis, adaptive study recommendations, an animated Pomodoro timer, and built-in authentication.

## Stack

- Backend and frontend: Django
- Database: PostgreSQL
- AI / ML: OpenCV + DeepFace
- Charts: Chart.js
- UI: Django templates + custom CSS + vanilla JavaScript

## Project Structure

```text
munnaproject/
├── core/
├── static/
│   ├── css/app.css
│   └── js/dashboard.js
├── study_assistant/
├── templates/
│   ├── auth/
│   ├── base.html
│   └── dashboard.html
├── .env.example
├── manage.py
├── requirements.txt
└── README.md
```

## Features

- Webcam emotion detection with simulated mode and real DeepFace mode
- Emotion-aware study recommendations
- Advanced Pomodoro timer with animated circular progress
- Productivity dashboard with study-time and mood-trend charts
- Login and signup using Django auth
- Theme toggle with premium dark and light UI
- Ambient focus sound section

## Setup

### 1. Create environment and install packages

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
copy .env.example .env
```

Important variables:

- `USE_SQLITE=True` for quick local testing
- `USE_SQLITE=False` to use PostgreSQL
- `ENABLE_REAL_EMOTION_DETECTION=True` to run DeepFace analysis

### 3. Database setup

For PostgreSQL:

```sql
CREATE DATABASE emotion_study_assistant;
```

Then update `.env` with your database credentials and set `USE_SQLITE=False`.

### 4. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create admin user

```bash
python manage.py createsuperuser
```

### 6. Start the server

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/`

## Models

- `UserProfile`
- `MoodLog`
- `StudySession`

## Emotion Mapping

- `tired` -> break reminders and recovery mode
- `sad` -> motivational support and gentle Pomodoro
- `focused` -> deep work recommendations
- `happy` -> momentum-based study suggestions
- `angry` -> cooldown-first flow
- `neutral` -> warm-up sprint

## Notes

- Webcam access happens in the browser and snapshots are sent to Django.
- If DeepFace is unavailable or disabled, the app falls back to simulated emotion data.
- The older React/FastAPI scaffold is not the active implementation now; use the Django app in the repo root.

# Study Guardian
An AI-based study assistant application.
