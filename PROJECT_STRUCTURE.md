# Project Structure - Study Assistant

This document provides a visual and descriptive overview of the system architecture and file organization for the **Study Assistant** project.

## Architecture Diagram

The following diagram illustrates the core components of the Django application and how they interact.

```mermaid
graph TD
    %% Main Project Container
    subgraph Root ["munnaproject (Project Root)"]
        
        %% Config/Settings
        subgraph Config ["Study Assistant Config"]
            SA["study_assistant/"] 
            SA_Set["settings.py"]
            SA_Urls["urls.py"]
            SA_WSGI["wsgi.py / asgi.py"]
        end

        %% Core Application
        subgraph CoreApp ["Core Application"]
            CR["core/"]
            CR_Mod["models.py (Database)"]
            CR_View["views.py (Request Handlers)"]
            CR_Svc["services.py (AI/Business Logic)"]
            CR_Sig["signals.py (Hooks)"]
            CR_Form["forms.py"]
            CR_Urls["urls.py (App Routes)"]
        end

        %% Frontend
        subgraph Frontend ["Frontend & User Interface"]
            TPL["templates/"]
            TPL_B["base.html (App Shell)"]
            TPL_A["auth/ (Login/Signup)"]
            TPL_D["dashboard.html"]
            TPL_S["study_lab.html"]
            
            STA["static/"]
            STA_JS["js/ (Interactive Logic)"]
            STA_CSS["css/ (Styling)"]
        end

        %% Environment & Data
        subgraph Data ["Environment & Storage"]
            DB["db.sqlite3"]
            ENV[".env (Security Keys)"]
            REQ["requirements.txt"]
        end

    end

    %% Connections
    SA_Urls --> CR_Urls
    CR_View --> CR_Mod
    CR_View --> CR_Svc
    CR_View --> TPL
    TPL --> STA
    CR_Svc --> ENV
```

---

## Directory Breakdown

### 📂 `core/`
The primary Django application containing the business logic.
- **`models.py`**: Defines the data structures for users, study materials, and logs.
- **`services.py`**: Contains specialized functions for AI integrations (like Groq/Gemini) and document processing.
- **`views.py`**: Orchestrates the flow between the models and the templates.

### 📂 `study_assistant/`
The project-level configuration folder.
- **`settings.py`**: Global settings, including database configuration, API endpoint registrations, and middleware.
- **`urls.py`**: The top-level URL dispatcher that routes requests to the `core` app.

### 📂 `templates/`
Contains HTML templates using Django's template engine.
- **`base.html`**: The parent template containing the main layout, sidebar, and design system.
- **`auth/`**: Templates for user registration and authentication.

### 📂 `static/`
Stores client-side assets.
- **`css/`**: Defined styles for the modern, premium aesthetic of the application.
- **`js/`**: Client-side logic for real-time dashboard updates and interactive features.

### 📂 `ganesh/` (Excluded from Diagram)
This is the Python Virtual Environment (venv). It contains all dependencies required to run the project.

---

> [!TIP]
> **Aesthetics Note**: The project follows a premium design philosophy with glassmorphism and modern HSL-based color palettes. Changes to global styling should be made in `static/css/` and `templates/base.html`.
