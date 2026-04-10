from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_outboundwhatsappmessage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activitylog",
            name="activity_type",
            field=models.CharField(
                choices=[
                    ("login", "Login"),
                    ("logout", "Logout"),
                    ("app_close", "App Close"),
                    ("emotion_check", "Emotion Check"),
                    ("study_session", "Study Session"),
                    ("theme_change", "Theme Change"),
                    ("parent_update", "Parent Update"),
                ],
                max_length=30,
            ),
        ),
    ]
