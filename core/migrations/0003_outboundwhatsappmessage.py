from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_userprofile_parent_last_summary_on_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutboundWhatsAppMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_number", models.CharField(max_length=32)),
                ("from_number", models.CharField(max_length=32)),
                ("body", models.TextField(blank=True)),
                ("media_urls", models.TextField(blank=True)),
                ("status_callback_url", models.URLField(blank=True)),
                ("twilio_sid", models.CharField(blank=True, db_index=True, max_length=64)),
                ("status", models.CharField(default="queued", max_length=40)),
                ("error_code", models.CharField(blank=True, max_length=32)),
                ("error_message", models.CharField(blank=True, max_length=255)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="outbound_whatsapp_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
