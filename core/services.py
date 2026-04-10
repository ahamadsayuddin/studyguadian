import base64
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from random import choice, uniform

import requests
from django.conf import settings
from django.utils import timezone
from google import genai

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
except Exception as exc:
    Client = None
    TwilioHttpClient = None
    print(f"[services] Twilio client import failed: {exc}")

cv2 = None
np = None
DeepFace = None
REAL_ENGINE_IMPORT_ERROR = ""

# ---------------------------------------------------------------------------
# Ambient audio tracks
# ---------------------------------------------------------------------------

AMBIENT_TRACKS = [
    {"name": "Lo-fi Rain", "url": "https://cdn.pixabay.com/download/audio/2022/03/10/audio_5e55ff8c75.mp3", "icon": "🌧"},
    {"name": "Forest Birds", "url": "https://cdn.pixabay.com/download/audio/2022/01/20/audio_d16737dc28.mp3", "icon": "🌿"},
    {"name": "Ocean Waves", "url": "https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0c6ff1b69.mp3", "icon": "🌊"},
    {"name": "White Noise", "url": "https://cdn.pixabay.com/download/audio/2021/08/09/audio_88447e769f.mp3", "icon": "🔲"},
    {"name": "Cafe Ambience", "url": "https://cdn.pixabay.com/download/audio/2022/02/07/audio_d1718ab41b.mp3", "icon": "☕"},
]

# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

FALLBACK_QUOTES = [
    {"content": "The secret of getting ahead is getting started.", "author": "Mark Twain"},
    {"content": "It always seems impossible until it's done.", "author": "Nelson Mandela"},
    {"content": "Don't watch the clock; do what it does. Keep going.", "author": "Sam Levenson"},
    {"content": "Success is the sum of small efforts repeated day in and day out.", "author": "Robert Collier"},
    {"content": "Believe you can and you're halfway there.", "author": "Theodore Roosevelt"},
]


def get_quote():
    quotes_api = getattr(settings, "QUOTES_API_URL", "")
    if quotes_api:
        try:
            resp = requests.get(quotes_api, timeout=3)
            if resp.ok:
                data = resp.json()
                return {"content": data.get("content", ""), "author": data.get("author", "")}
        except Exception:
            pass
    return choice(FALLBACK_QUOTES)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

RECOMMENDATIONS = {
    "happy": [
        "Great energy! Tackle your hardest subject now.",
        "You're in a great flow state — push through challenging material.",
        "Use this positivity to write notes or teach what you know.",
    ],
    "sad": [
        "Take a 10-minute walk to reset your mind.",
        "Start with something easy to build momentum.",
        "Listening to lo-fi music may help you focus.",
    ],
    "angry": [
        "Try box breathing: 4s in, 4s hold, 4s out.",
        "Write down what's bothering you, then set it aside.",
        "A short break can reset your focus.",
    ],
    "neutral": [
        "Good baseline — try a Pomodoro session.",
        "Review your goals for today.",
        "Mix active recall with reading for best retention.",
    ],
    "tired": [
        "Take a 20-minute power nap if possible.",
        "Hydrate and have a light snack.",
        "Switch to lighter review tasks instead of new material.",
    ],
    "focused": [
        "You're in the zone — keep it going!",
        "Deep work mode: silence notifications.",
        "Try tackling the most complex topic while focus is high.",
    ],
}


def get_recommendations(emotion):
    return RECOMMENDATIONS.get(emotion, RECOMMENDATIONS["neutral"])


# ---------------------------------------------------------------------------
# Weekly / mood analytics
# ---------------------------------------------------------------------------

def build_weekly_focus_data(sessions):
    today = timezone.localdate()
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    label_map = {d: d.strftime("%a") for d in days}
    data = {d: 0 for d in days}
    for session in sessions:
        date = timezone.localtime(session.started_at).date()
        if date in data:
            data[date] += session.duration_minutes
    return {
        "labels": [label_map[d] for d in days],
        "data": [data[d] for d in days],
    }


def build_mood_trends(moods):
    emotion_map = {"happy": 5, "focused": 4, "neutral": 3, "tired": 2, "sad": 1, "angry": 0}
    recent = moods[:7][::-1]
    return {
        "labels": [m.captured_at.strftime("%d %b") for m in recent],
        "data": [emotion_map.get(m.emotion, 3) for m in recent],
    }


# ---------------------------------------------------------------------------
# Twilio / WhatsApp helpers
# ---------------------------------------------------------------------------

def is_twilio_whatsapp_sandbox(from_number):
    """Return True if the configured Twilio number looks like a sandbox number."""
    if not from_number:
        return False
    sandbox_numbers = {"+14155238886", "14155238886"}
    clean = from_number.strip().replace("whatsapp:", "")
    return clean in sandbox_numbers


def _format_whatsapp_number(number):
    number = number.strip()
    if not number.startswith("+"):
        number = "+" + number
    return number


def get_parent_message_channel():
    sms_from = getattr(settings, "TWILIO_SMS_FROM", "").strip()
    if sms_from:
        return "sms"

    whatsapp_from = getattr(settings, "TWILIO_WHATSAPP_FROM", "").strip()
    if whatsapp_from:
        return "whatsapp"

    return ""


def get_parent_message_channel_label():
    channel = get_parent_message_channel()
    if channel == "sms":
        return "SMS"
    if channel == "whatsapp":
        return "WhatsApp"
    return "Twilio message"


def _format_e164_number(number):
    number = str(number or "").strip().replace("whatsapp:", "")
    number = "".join(char for char in number if char.isdigit() or char == "+")
    if number and not number.startswith("+"):
        number = f"+{number}"
    return number


def send_parent_message(profile, message_text):
    """Send a Twilio message to the parent and return a result dict."""
    to_number = (profile.parent_whatsapp_number or "").strip()
    if not to_number:
        return {"sent": False, "reason": "No parent phone number configured.", "to": ""}

    to_number = _format_e164_number(to_number)

    # Twilio message body truncation for safer delivery across channels.
    if len(message_text) > 1500:
        message_text = message_text[:1490] + "... [truncated]"

    result = send_twilio_message(to_number=to_number, body=message_text, user=profile.user)
    result.setdefault("to", to_number)
    return result


def send_parent_summary(profile, summary_text):
    return send_parent_message(profile, summary_text)


def build_parent_presence_message(user, sessions, action):
    name = user.first_name or user.username
    total_mins = sum(s.duration_minutes for s in sessions)
    now_str = timezone.localtime().strftime("%Y-%m-%d %I:%M %p")
    return (
        f"Hi! {name} has {action}.\n"
        f"Total study time logged: {total_mins} minutes.\n"
        f"Time: {now_str}"
    )


def build_parent_summary(user, sessions, moods, activities):
    name = user.first_name or user.username
    today = timezone.localdate()
    today_sessions = [s for s in sessions if timezone.localtime(s.started_at).date() == today]
    today_mins = sum(s.duration_minutes for s in today_sessions)
    latest_mood = moods[0].emotion if moods else "unknown"
    recent_activities = [a.detail for a in activities[:5] if a.detail]
    activity_lines = "\n  - ".join(recent_activities) if recent_activities else "No recent activity"

    return (
        f"Daily Study Summary for {name}:\n"
        f"Date: {today.strftime('%Y-%m-%d')}\n"
        f"Study time today: {today_mins} minutes\n"
        f"Latest mood: {latest_mood}\n"
        f"Recent activity:\n  - {activity_lines}"
    )


def record_whatsapp_status_callback(post_data):
    """Record a Twilio status callback. Returns dict with sid, status, message_log."""
    sid = post_data.get("MessageSid", "")
    status = post_data.get("MessageStatus", "unknown")
    message_log = None

    try:
        from .models import OutboundWhatsAppMessage
        if sid:
            message_log = OutboundWhatsAppMessage.objects.filter(twilio_sid=sid).first()
            if message_log:
                message_log.status = status
                error_code = post_data.get("ErrorCode", "")
                if error_code:
                    message_log.error_code = error_code
                    message_log.error_message = post_data.get("ErrorMessage", "")
                message_log.raw_payload = post_data
                message_log.save(update_fields=["status", "error_code", "error_message", "raw_payload", "updated_at"])
    except Exception:
        pass

    return {"sid": sid, "status": status, "message_log": message_log}


# ---------------------------------------------------------------------------
# Twilio sending
# ---------------------------------------------------------------------------

def send_twilio_message(to_number, body, user=None):
    if not Client or not TwilioHttpClient:
        print("Twilio client is not available.")
        return {"sent": False, "reason": "Twilio Not Installed", "to": to_number}

    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    sms_from = getattr(settings, "TWILIO_SMS_FROM", "").strip()
    whatsapp_from = getattr(settings, "TWILIO_WHATSAPP_FROM", "").strip()
    channel = get_parent_message_channel()

    if not all([account_sid, auth_token]) or not channel:
        print("Twilio credentials missing.")
        return {"sent": False, "reason": "Config Missing", "to": to_number}

    if channel == "sms":
        from_formatted = _format_e164_number(sms_from)
        to_formatted = _format_e164_number(to_number)
        status_callback = ""
    else:
        from_formatted = whatsapp_from if whatsapp_from.startswith("whatsapp:") else f"whatsapp:{_format_whatsapp_number(whatsapp_from)}"
        to_formatted = to_number if str(to_number).startswith("whatsapp:") else f"whatsapp:{_format_whatsapp_number(to_number)}"
        status_callback = getattr(settings, "TWILIO_WHATSAPP_STATUS_CALLBACK", "").strip()

    client = Client(account_sid, auth_token)
    try:
        create_kwargs = {
            "from_": from_formatted,
            "body": body,
            "to": to_formatted,
        }
        if status_callback:
            create_kwargs["status_callback"] = status_callback

        message = client.messages.create(**create_kwargs)
        print(f"Twilio {channel} message SID: {message.sid}")

        # Log message to DB
        try:
            from .models import OutboundWhatsAppMessage
            OutboundWhatsAppMessage.objects.create(
                user=user,
                to_number=to_number,
                from_number=from_formatted,
                body=body,
                status_callback_url=status_callback,
                twilio_sid=message.sid,
                status="queued",
            )
        except Exception:
            pass

        return {"sent": True, "sid": message.sid, "to": to_number, "channel": channel}
    except Exception as exc:
        print(f"Twilio error: {exc}")
        return {"sent": False, "reason": str(exc), "to": to_number, "channel": channel}


def send_whatsapp_message(to_number, body, user=None):
    """Backward-compatible wrapper for older call sites."""
    return send_twilio_message(to_number=to_number, body=body, user=user)


# ---------------------------------------------------------------------------
# Test results → Parent
# ---------------------------------------------------------------------------

def send_test_results_to_parent(profile, total, correct, time_taken, performance):
    if not profile.parent_whatsapp_number or not profile.parent_updates_enabled:
        return {"sent": False, "reason": "Parent updates disabled or number missing."}

    message = (
        f"Test results for {profile.user.first_name or profile.user.username}:\n"
        f"Correct Answers: {correct} / {total}\n"
        f"Time Taken: {time_taken} seconds\n"
        f"Performance: {performance}\n"
    )
    return send_parent_message(profile, message)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# AI Multi-Provider Helpers (Gemini & Groq)
# ---------------------------------------------------------------------------

_genai_client = None
_groq_client = None

def _get_gemini_client():
    global _genai_client
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not _genai_client and api_key:
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client

def _get_groq_client():
    global _groq_client
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not _groq_client and api_key and Groq:
        _groq_client = Groq(api_key=api_key)
    return _groq_client

def _resolve_ai_provider():
    preferred = getattr(settings, "AI_PROVIDER", "groq").lower()
    provider_order = [preferred]
    for fallback in ("groq", "gemini"):
        if fallback not in provider_order:
            provider_order.append(fallback)

    for provider in provider_order:
        if provider == "groq":
            client = _get_groq_client()
            if client:
                model_id = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
                return client, model_id, "groq"
            continue

        if provider == "gemini":
            client = _get_gemini_client()
            if client:
                model_id = getattr(settings, "GEMINI_CHAT_MODEL", "gemini-2.0-flash")
                return client, model_id, "gemini"

    if getattr(settings, "GROQ_API_KEY", "") and not Groq and getattr(settings, "GEMINI_API_KEY", ""):
        return None, None, "Groq library failed to load, and Gemini fallback could not be initialized."
    if getattr(settings, "GROQ_API_KEY", "") and not Groq:
        return None, None, "Groq library failed to load. Install the Groq package or switch AI_PROVIDER to gemini."
    if getattr(settings, "GROQ_API_KEY", "") or getattr(settings, "GEMINI_API_KEY", ""):
        return None, None, "Configured AI provider could not be initialized."
    return None, None, "No AI provider is configured. Add a GROQ_API_KEY or GEMINI_API_KEY."

def _call_ai_with_retry(fn, *args, **kwargs):
    client, model_id, provider = _resolve_ai_provider()
    if not client:
        return provider

    max_retries = 5 if provider == "groq" else 8
    for attempt in range(max_retries):
        try:
            return fn(client, model_id, provider, *args, **kwargs)
        except Exception as exc:
            err = str(exc).lower()
            is_quota = any(x in err for x in ["429", "quota", "limit", "rate"])
            
            if is_quota and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 8.0 + uniform(0.5, 1.5)
                print(f"[services] {provider.upper()} Quota error (Attempt {attempt+1}/{max_retries}). Retrying...")
                time.sleep(wait_time)
                continue
            
            if is_quota:
                return f"AI Quota temporary exhausted ({provider.capitalize()} limit). Please wait a moment."
            
            print(f"[services] {provider.upper()} error: {exc}")
            return f"AI error: {exc}"

def _extract_mcq_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("mcqs", "questions", "quiz", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None

def _is_valid_mcq_list(mcqs):
    if not isinstance(mcqs, list) or not mcqs:
        return False

    for item in mcqs:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("question"), str) or not item.get("question").strip():
            return False
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4 or not all(isinstance(opt, str) and opt.strip() for opt in options):
            return False
        answer = item.get("answer")
        if not isinstance(answer, str) or answer not in options:
            return False
    return True

def build_ai_study_reply(question, history=None):
    def _fn(client, model_id, provider, q, h):
        system_prompt = "You are a helpful AI Study Assistant. Provide clear, academic, and encouraging answers."
        context = ""
        if h:
            for msg in h[-6:]:
                context += f"{'User' if msg['role'] == 'user' else 'AI'}: {msg['content']}\n"
        
        full_query = f"System: {system_prompt}\n{context}User: {q}"
        
        if provider == "groq":
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    *[{"role": m["role"], "content": m["content"]} for m in (h or [])[-6:]],
                    {"role": "user", "content": q}
                ],
                model=model_id,
            )
            return chat_completion.choices[0].message.content.strip()
        else:
            response = client.models.generate_content(model=model_id, contents=full_query)
            return response.text.strip()
    
    return _call_ai_with_retry(_fn, question, history)


def extract_text_from_pdf(file_path):
    try:
        import pypdf
        text = ""
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                extr = page.extract_text()
                if extr:
                    text += extr + "\n"
        return text.strip()
    except Exception as exc:
        return f"Error extracting PDF: {exc}"


def explain_document_with_gemini(text):
    def _fn(client, model_id, provider, t):
        prompt = f"Summarize and explain the following document. Highlight the most important key concepts and takeaways in an easy-to-understand way:\n\n{t[:10000]}"
        
        if provider == "groq":
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert tutor. Provide clear and structured explanations."},
                    {"role": "user", "content": prompt}
                ],
                model=model_id,
            )
            return chat_completion.choices[0].message.content.strip()
        else:
            response = client.models.generate_content(model=model_id, contents=prompt)
            return response.text.strip()
    
    return _call_ai_with_retry(_fn, text)


def generate_mcqs_with_gemini(text, count):
    # This function is now provider-aware via _call_ai_with_retry
    def _fn(client, model_id, provider, t, c):
        prompt = (
            f"Generate exactly {c} multiple choice questions based on the following text.\n"
            f"Output must be a JSON list of objects. Each object must have keys: 'question', 'options' (a list of 4 strings), and 'answer' (one of the options exactly).\n"
            f"Text: {t[:10000]}"
        )
        
        if provider == "groq":
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a quiz generator. Always output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=model_id,
                response_format={"type": "json_object"}
            )
            return chat_completion.choices[0].message.content.strip()
        else:
            # Use response_mime_type for better stability if supported by model
            response = client.models.generate_content(
                model=model_id, 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            return response.text.strip() if response.text else ""
    
    content = _call_ai_with_retry(_fn, text, count)
    
    if not isinstance(content, str):
        return "Failed to communicate with AI."
    
    if (
        "AI Quota temporary exhausted" in content
        or "API Quota" in content
        or content.startswith("AI error:")
        or "could not be initialized" in content
        or "No AI provider is configured" in content
        or "Groq library failed to load" in content
    ):
        return content
    
    if not content:
        return "AI returned an empty response. Please try again with different content."
    
    try:
        # Robust JSON extraction
        clean_content = content.strip()
        if "```json" in clean_content:
            clean_content = clean_content.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_content:
            clean_content = clean_content.split("```")[1].strip()

        parsed = None
        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            obj_start = clean_content.find("{")
            obj_end = clean_content.rfind("}")
            if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
                try:
                    parsed = json.loads(clean_content[obj_start : obj_end + 1])
                except json.JSONDecodeError:
                    parsed = None

            if parsed is None:
                list_start = clean_content.find("[")
                list_end = clean_content.rfind("]")
                if list_start != -1 and list_end != -1 and list_end > list_start:
                    parsed = json.loads(clean_content[list_start : list_end + 1])

        mcqs = _extract_mcq_list(parsed)
        if _is_valid_mcq_list(mcqs):
            return mcqs
        return "AI returned MCQs in an unexpected format. Please try again."
    except Exception as exc:
        msg = f"MCQ parsing failed: {exc}"
        print(f"[services] Content received: {content[:200]}...") # Log for debugging
        print(f"[services] {msg}")
        return msg
