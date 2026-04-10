from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    THEME_CHOICES = [("dark", "Dark"), ("light", "Light")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    theme_preference = models.CharField(max_length=10, choices=THEME_CHOICES, default="dark")
    streak_count = models.PositiveIntegerField(default=1)
    daily_goal_minutes = models.PositiveIntegerField(default=180)
    parent_whatsapp_number = models.CharField(max_length=20, blank=True)
    parent_updates_enabled = models.BooleanField(default=False)
    parent_last_summary_on = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} profile"


class MoodLog(models.Model):
    EMOTION_CHOICES = [
        ("happy", "Happy"),
        ("sad", "Sad"),
        ("angry", "Angry"),
        ("neutral", "Neutral"),
        ("tired", "Tired"),
        ("focused", "Focused"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mood_logs")
    emotion = models.CharField(max_length=20, choices=EMOTION_CHOICES)
    confidence = models.FloatField(default=0)
    energy_score = models.FloatField(default=0)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.user.username} - {self.emotion}"


class StudySession(models.Model):
    FOCUS_MODES = [("flow", "25 / 5"), ("deep", "50 / 10"), ("reset", "Reset")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="study_sessions")
    focus_mode = models.CharField(max_length=20, choices=FOCUS_MODES, default="flow")
    duration_minutes = models.PositiveIntegerField(default=25)
    break_minutes = models.PositiveIntegerField(default=5)
    productivity_score = models.FloatField(default=0)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user.username} - {self.focus_mode} - {self.duration_minutes}m"


class ActivityLog(models.Model):
    ACTIVITY_CHOICES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("app_close", "App Close"),
        ("emotion_check", "Emotion Check"),
        ("study_session", "Study Session"),
        ("theme_change", "Theme Change"),
        ("parent_update", "Parent Update"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_logs")
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_CHOICES)
    detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.activity_type}"


class OutboundWhatsAppMessage(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="outbound_whatsapp_messages",
        blank=True,
        null=True,
    )
    to_number = models.CharField(max_length=32)
    from_number = models.CharField(max_length=32)
    body = models.TextField(blank=True)
    media_urls = models.TextField(blank=True)
    status_callback_url = models.URLField(blank=True)
    twilio_sid = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=40, default="queued")
    error_code = models.CharField(max_length=32, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.twilio_sid or f"{self.from_number} -> {self.to_number}"


class UploadedDocument(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="uploaded_documents")
    filename = models.CharField(max_length=255)
    parsed_text = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.filename}"


class TestResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="test_results")
    total_questions = models.PositiveIntegerField()
    correct_answers = models.PositiveIntegerField()
    time_taken_seconds = models.PositiveIntegerField(default=0)
    performance = models.CharField(max_length=50, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.correct_answers}/{self.total_questions}"


class PendingTest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pending_tests")
    document = models.ForeignKey(UploadedDocument, on_delete=models.CASCADE)
    mcq_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pending Test for {self.user.username} - {self.document.filename}"
