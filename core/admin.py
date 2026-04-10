from django.contrib import admin

from .models import ActivityLog, MoodLog, OutboundWhatsAppMessage, StudySession, UserProfile

admin.site.register(UserProfile)
admin.site.register(MoodLog)
admin.site.register(StudySession)
admin.site.register(ActivityLog)
admin.site.register(OutboundWhatsAppMessage)
