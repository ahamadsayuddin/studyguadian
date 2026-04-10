import json
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import ParentContactForm, SignupForm, StyledAuthenticationForm
from .models import ActivityLog, MoodLog, StudySession, UserProfile, UploadedDocument, TestResult
from .services import (
    AMBIENT_TRACKS,
    build_parent_presence_message,
    build_parent_summary,
    build_mood_trends,
    build_weekly_focus_data,
    get_parent_message_channel,
    get_parent_message_channel_label,
    get_quote,
    get_recommendations,
    is_twilio_whatsapp_sandbox,
    record_whatsapp_status_callback,
    send_parent_message,
    send_parent_summary,
    explain_document_with_gemini,
    generate_mcqs_with_gemini,
    extract_text_from_pdf,
    send_test_results_to_parent,
    build_ai_study_reply,
)
import os
import tempfile


class StudyLoginView(LoginView):
    template_name = "auth/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


class StudyLogoutView(LogoutView):
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            sessions = list(request.user.study_sessions.all())
            ActivityLog.objects.create(user=request.user, activity_type="logout", detail="Logged out")
            if profile.parent_updates_enabled and profile.parent_whatsapp_number:
                try:
                    message_text = build_parent_presence_message(request.user, sessions, "closed the app")
                    send_parent_message(profile, message_text)
                    ActivityLog.objects.create(
                        user=request.user,
                        activity_type="parent_update",
                        detail="Logout alert sent",
                    )
                except Exception:
                    pass
        return super().post(request, *args, **kwargs)


def _is_ajax_json_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.email = form.cleaned_data["email"]
        user.first_name = form.cleaned_data["first_name"]
        user.save()
        UserProfile.objects.get_or_create(user=user)
        login(request, user)
        messages.success(request, "Your AI study workspace is ready.")
        return redirect("dashboard")

    return render(request, "auth/signup.html", {"form": form})


def get_base_context(request):
    """Common context needed for the sidebar and layout across all 6 pages."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return {
        "profile": profile,
        "request": request,
        "ai_enabled": bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY),
    }


@login_required
@require_GET
def dashboard_view(request):
    sessions = list(request.user.study_sessions.all())
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.localdate()

    # App Open Alert and Daily Summary Auto-send (only on initial dashboard load)
    if not request.session.get("parent_open_alert_sent"):
        ActivityLog.objects.create(user=request.user, activity_type="login", detail="Opened dashboard")
        request.session["activity_login_date"] = today.isoformat()
        if profile.parent_updates_enabled and profile.parent_whatsapp_number:
            try:
                open_message = build_parent_presence_message(request.user, sessions, "opened the app")
                send_parent_message(profile, open_message)
                ActivityLog.objects.create(user=request.user, activity_type="parent_update", detail="Open alert sent")
                request.session["parent_open_alert_sent"] = True
            except Exception:
                pass

    today_focus_minutes = sum(
        session.duration_minutes
        for session in sessions
        if timezone.localtime(session.started_at).date() == today
    )

    context = get_base_context(request)
    context.update({
        "today_focus_minutes": today_focus_minutes or 0,
        "streak_count": profile.streak_count,
        "quote": get_quote(),
    })
    return render(request, "dashboard.html", context)


@login_required
@require_GET
def study_lab_view(request):
    return render(request, "study_lab.html", get_base_context(request))


@login_required
@require_GET
def assessment_center_view(request):
    from .models import PendingTest, UploadedDocument
    pending = PendingTest.objects.filter(user=request.user).first()
    pending_test_json = json.dumps(pending.mcq_json) if pending else "null"
    
    # Get user's documents for the dropdown
    user_docs = UploadedDocument.objects.filter(user=request.user).only("id", "filename")
    
    context = get_base_context(request)
    context.update({
        "pending_test_json": pending_test_json,
        "user_docs": user_docs,
        "mcq_url": reverse("generate_mcq"),
    })
    return render(request, "assessment_center.html", context)


@login_required
@require_GET
def focus_zone_view(request):
    context = get_base_context(request)
    context.update({
        "ambient_tracks_json": json.dumps(AMBIENT_TRACKS),
    })
    return render(request, "focus_zone.html", context)


@login_required
@require_GET
def analytics_view(request):
    sessions = list(request.user.study_sessions.all())
    moods = list(request.user.mood_logs.all())
    latest_emotion = moods[0].emotion if moods else "focused"
    
    context = get_base_context(request)
    context.update({
        "weekly_study_time_json": json.dumps(build_weekly_focus_data(sessions)),
        "mood_trends_json": json.dumps(build_mood_trends(moods)),
        "recommendations_json": json.dumps(get_recommendations(latest_emotion)),
        "latest_emotion": latest_emotion,
    })
    return render(request, "analytics.html", context)


@login_required
@require_GET
def guardian_connect_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    saved_parent_number = profile.parent_whatsapp_number
    message_channel = get_parent_message_channel()
    message_channel_label = get_parent_message_channel_label()
    whatsapp_delivery_note = None
    if saved_parent_number:
        whatsapp_delivery_note = f"Current saved parent {message_channel_label} target: {saved_parent_number}."
    if message_channel == "whatsapp" and is_twilio_whatsapp_sandbox(settings.TWILIO_WHATSAPP_FROM):
        whatsapp_delivery_note = (whatsapp_delivery_note or "") + " Twilio sandbox active undi, so joined numbers ki matrame messages vellavachu."
    if not message_channel:
        whatsapp_delivery_note = "Configure either TWILIO_SMS_FROM for SMS or TWILIO_WHATSAPP_FROM for WhatsApp."

    context = get_base_context(request)
    context.update({
        "parent_contact_form": ParentContactForm(instance=profile),
        "whatsapp_delivery_note": whatsapp_delivery_note,
        "message_channel": message_channel,
        "message_channel_label": message_channel_label,
        "uses_whatsapp_sandbox": message_channel == "whatsapp" and is_twilio_whatsapp_sandbox(settings.TWILIO_WHATSAPP_FROM),
    })
    return render(request, "guardian_connect.html", context)


@login_required
@require_POST
def upload_document_view(request):
    if "document" not in request.FILES:
        return JsonResponse({"error": "No document provided."}, status=400)
    
    file_obj = request.FILES["document"]
    filename = file_obj.name
    
    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, 'wb') as f:
        for chunk in file_obj.chunks():
            f.write(chunk)
            
    try:
        if filename.lower().endswith(".pdf"):
            text = extract_text_from_pdf(temp_path)
        else:
            with open(temp_path, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception as exc:
        os.remove(temp_path)
        return JsonResponse({"error": f"Failed to read file: {exc}"}, status=400)
    
    os.remove(temp_path)
    
    if not text or not text.strip():
        return JsonResponse({"error": "No text found in the document."}, status=400)
        
    doc = UploadedDocument.objects.create(user=request.user, filename=filename, parsed_text=text)
    
    explanation = explain_document_with_gemini(text)
    
    # Notify parent if enabled
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.parent_updates_enabled and profile.parent_whatsapp_number:
        try:
            parent_msg = f"User {request.user.first_name or request.user.username} just uploaded and analyzed a document: {filename}\n\nAI Explanation:\n{explanation}"
            send_parent_message(profile, parent_msg)
        except Exception:
            pass
    
    return JsonResponse({
        "status": "ok",
        "document_id": doc.id,
        "explanation": explanation
    })


@login_required
@require_POST
def generate_mcq_view(request):
    payload = json.loads(request.body or "{}")
    doc_id = payload.get("document_id")
    count = int(payload.get("count", 10))
    
    try:
        doc = UploadedDocument.objects.get(id=doc_id, user=request.user)
    except UploadedDocument.DoesNotExist:
        return JsonResponse({"error": "Document not found."}, status=404)
        
    mcqs = generate_mcqs_with_gemini(doc.parsed_text, count)
    if isinstance(mcqs, str):
        return JsonResponse({"error": mcqs}, status=500)
    if not mcqs:
        return JsonResponse({"error": "Failed to generate MCQs (Quota exceeded or parsing error)."}, status=500)
    
    # Persist the test for the user
    from .models import PendingTest
    PendingTest.objects.filter(user=request.user).delete() # One pending test at a time
    PendingTest.objects.create(user=request.user, document=doc, mcq_json=mcqs)
        
    return JsonResponse({"status": "ok", "mcqs": mcqs})


@login_required
@require_POST
def submit_test_view(request):
    payload = json.loads(request.body or "{}")
    total = int(payload.get("total", 0))
    correct = int(payload.get("correct", 0))
    time_taken = int(payload.get("time_taken", 0))
    malpractice = bool(payload.get("malpractice", False))
    reason = str(payload.get("reason", "")).strip()
    
    if total == 0:
        return JsonResponse({"error": "Invalid test data."}, status=400)
    
    # Clear pending test
    from .models import PendingTest
    PendingTest.objects.filter(user=request.user).delete()
        
    ratio = correct / total
    if malpractice:
        performance = f"Malpractice Detected ({reason or 'General'})"
    elif ratio >= 0.9:
        performance = "Excellent"
    elif ratio >= 0.7:
        performance = "Good"
    elif ratio >= 0.5:
        performance = "Average"
    else:
        performance = "Needs Practice"
        
    result = TestResult.objects.create(
        user=request.user,
        total_questions=total,
        correct_answers=correct,
        time_taken_seconds=time_taken,
        performance=performance
    )
    
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    send_test_results_to_parent(profile, total, correct, time_taken, performance)
    
    return JsonResponse({
        "status": "ok",
        "result_id": result.id,
        "performance": performance
    })


@login_required
@require_POST
def ask_study_ai_view(request):
    payload = json.loads(request.body or "{}")
    question = payload.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "Question is empty."}, status=400)
    
    history = request.session.get("study_ai_history", [])
    reply = build_ai_study_reply(question, history)
    
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply})
    request.session["study_ai_history"] = history[-20:] # Keep last 10 exchanges

    # Notify parent if enabled (summary of the answer)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.parent_updates_enabled and profile.parent_whatsapp_number:
        try:
            parent_msg = f"Study AI Chat Update for {request.user.first_name or request.user.username}:\nQ: {question}\nAI: {reply}"
            send_parent_message(profile, parent_msg)
        except Exception:
            pass
    
    return JsonResponse({"status": "ok", "reply": reply})


@login_required
@require_POST
def clear_study_ai_view(request):
    request.session["study_ai_history"] = []
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def save_session_view(request):
    payload = json.loads(request.body or "{}")
    session = StudySession.objects.create(
        user=request.user,
        focus_mode=payload.get("focus_mode", "flow"),
        duration_minutes=int(payload.get("duration_minutes", 25)),
        break_minutes=int(payload.get("break_minutes", 5)),
        productivity_score=float(payload.get("productivity_score", 0)),
        completed=bool(payload.get("completed", False)),
        completed_at=timezone.now() if payload.get("completed", False) else None,
    )
    ActivityLog.objects.create(
        user=request.user,
        activity_type="study_session",
        detail=f"{session.duration_minutes} min {session.focus_mode} session completed",
    )
    return JsonResponse({"status": "ok", "session_id": session.id})


@login_required
@require_POST
def update_theme_view(request):
    payload = json.loads(request.body or "{}")
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.theme_preference = payload.get("theme", "dark")
    profile.save(update_fields=["theme_preference"])
    ActivityLog.objects.create(
        user=request.user,
        activity_type="theme_change",
        detail=f"Theme changed to {profile.theme_preference}",
    )
    return JsonResponse({"status": "ok", "theme": profile.theme_preference})


@login_required
@require_POST
def update_parent_contact_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    form = ParentContactForm(request.POST, instance=profile)
    if form.is_valid():
        saved_profile = form.save()
        channel_label = get_parent_message_channel_label()
        message = f"Parent {channel_label} settings updated. Current target: {saved_profile.parent_whatsapp_number or 'Not set'}"
        send_result = None
        if saved_profile.parent_updates_enabled and saved_profile.parent_whatsapp_number:
            confirmation_text = (
                f"Parent notifications enabled for {request.user.first_name or request.user.username}.\n"
                f"Target number confirmed: {saved_profile.parent_whatsapp_number}\n"
                f"Time: {timezone.localtime().strftime('%Y-%m-%d %I:%M %p')}"
            )
            send_result = send_parent_message(saved_profile, confirmation_text)
            if send_result["sent"]:
                ActivityLog.objects.create(
                    user=request.user,
                    activity_type="parent_update",
                    detail=f"Parent contact confirmation sent to {send_result.get('to', saved_profile.parent_whatsapp_number)}",
                )
                message = f"{message}. Confirmation sent to {send_result.get('to', saved_profile.parent_whatsapp_number)}."
            else:
                message = f"{message}. Confirmation not sent: {send_result['reason']} Target: {send_result.get('to', saved_profile.parent_whatsapp_number)}"
        if _is_ajax_json_request(request):
            return JsonResponse({
                "status": "ok",
                "message": message,
                "target": saved_profile.parent_whatsapp_number or "",
                "enabled": saved_profile.parent_updates_enabled,
                "confirmation_sent": bool(send_result and send_result.get("sent")),
            })
        messages.success(request, message)
    else:
        error_text = form.errors.as_text()
        if _is_ajax_json_request(request):
            return JsonResponse({"status": "error", "error": error_text}, status=400)
        messages.error(request, error_text)
    return redirect("dashboard")


@login_required
@require_POST
def send_parent_update_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.parent_whatsapp_number:
        message = "Add a parent phone number first."
        if _is_ajax_json_request(request):
            return JsonResponse({"status": "error", "error": message}, status=400)
        messages.error(request, message)
        return redirect("dashboard")

    sessions = list(request.user.study_sessions.all())
    moods = list(request.user.mood_logs.all())
    activities = list(request.user.activity_logs.all())

    try:
        summary_text = build_parent_summary(request.user, sessions, moods, activities)
        result = send_parent_summary(profile, summary_text)
        if result["sent"]:
            today = timezone.localdate()
            profile.parent_last_summary_on = today
            profile.save(update_fields=["parent_last_summary_on"])
            ActivityLog.objects.create(user=request.user, activity_type="parent_update", detail="Manual summary sent")
            message = f"Parent summary sent to {result.get('to', profile.parent_whatsapp_number)}."
            if _is_ajax_json_request(request):
                return JsonResponse({"status": "ok", "message": message, "target": result.get("to", "")})
            messages.success(request, message)
        else:
            error_text = f"{result['reason']} Target: {result.get('to', profile.parent_whatsapp_number)}"
            if _is_ajax_json_request(request):
                return JsonResponse({"status": "error", "error": error_text, "target": result.get("to", "")}, status=400)
            messages.error(request, error_text)
    except Exception as exc:
        error_text = f"Parent summary failed: {exc}"
        if _is_ajax_json_request(request):
            return JsonResponse({"status": "error", "error": error_text}, status=500)
        messages.error(request, error_text)
    return redirect("dashboard")


@login_required
@require_POST
def send_test_parent_whatsapp_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.parent_whatsapp_number:
        message = "Add a parent phone number first."
        if _is_ajax_json_request(request):
            return JsonResponse({"status": "error", "error": message}, status=400)
        messages.error(request, message)
        return redirect("dashboard")

    test_message = (
        f"Test {get_parent_message_channel_label()} message from Study Assistant for {request.user.first_name or request.user.username}.\n"
        f"Time: {timezone.localtime().strftime('%Y-%m-%d %I:%M %p')}"
    )
    try:
        result = send_parent_message(profile, test_message)
        if result["sent"]:
            ActivityLog.objects.create(
                user=request.user,
                activity_type="parent_update",
                detail=f"Test {get_parent_message_channel_label()} sent",
            )
            message = f"Test {get_parent_message_channel_label()} message sent to {result.get('to', profile.parent_whatsapp_number)}."
            if _is_ajax_json_request(request):
                return JsonResponse({"status": "ok", "message": message, "target": result.get("to", "")})
            messages.success(request, message)
        else:
            error_text = f"{result['reason']} Target: {result.get('to', profile.parent_whatsapp_number)}"
            if _is_ajax_json_request(request):
                return JsonResponse({"status": "error", "error": error_text, "target": result.get("to", "")}, status=400)
            messages.error(request, error_text)
    except Exception as exc:
        error_text = f"Test {get_parent_message_channel_label()} failed: {exc}"
        if _is_ajax_json_request(request):
            return JsonResponse({"status": "error", "error": error_text}, status=500)
        messages.error(request, error_text)
    return redirect("dashboard")


@csrf_exempt
@login_required
@require_POST
def parent_presence_event_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.parent_updates_enabled or not profile.parent_whatsapp_number:
        return JsonResponse({"status": "skipped"})

    event_type = request.POST.get("event_type", "close")
    if event_type not in {"close"}:
        return JsonResponse({"status": "ignored"})

    if request.session.get("parent_close_alert_sent"):
        return JsonResponse({"status": "duplicate"})

    sessions = list(request.user.study_sessions.all())
    ActivityLog.objects.create(user=request.user, activity_type="app_close", detail="Browser tab closed")
    try:
        message_text = build_parent_presence_message(request.user, sessions, "closed the app")
        result = send_parent_message(profile, message_text)
        if result["sent"]:
            ActivityLog.objects.create(user=request.user, activity_type="parent_update", detail="Close alert sent")
            request.session["parent_close_alert_sent"] = True
            return JsonResponse({"status": "sent"})
        return JsonResponse({"status": "skipped", "reason": result["reason"]})
    except Exception as exc:
        return JsonResponse({"status": "error", "reason": str(exc)}, status=500)


@csrf_exempt
@require_POST
def twilio_whatsapp_status_callback_view(request):
    callback_result = record_whatsapp_status_callback(request.POST.dict())
    sid = callback_result.get("sid", "")
    status = callback_result.get("status", "unknown")
    message_log = callback_result.get("message_log")

    if message_log and message_log.user_id:
        ActivityLog.objects.create(
            user=message_log.user,
            activity_type="parent_update",
            detail=f"WhatsApp status for {sid or 'unknown'} changed to {status}",
        )

    return JsonResponse({"status": "ok", "message_sid": sid, "message_status": status})
