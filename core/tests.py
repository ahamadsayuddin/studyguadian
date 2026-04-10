from unittest.mock import patch

from django.test import SimpleTestCase
from django.test.utils import override_settings

from .services import build_ai_study_reply, get_parent_message_channel, get_parent_message_channel_label


class StudyAiFallbackTests(SimpleTestCase):
    @patch("core.services.ask_openai_study_assistant", side_effect=Exception("429 insufficient_quota"))
    def test_fallback_definition_question_gives_useful_topic_answer(self, _mock_ai):
        reply = build_ai_study_reply("What is osmosis?", emotion="neutral")

        self.assertIn("osmosis", reply.lower())
        self.assertNotIn("ask one doubt at a time", reply.lower())
        self.assertTrue("water" in reply.lower() or "plants" in reply.lower())


class TwilioChannelSelectionTests(SimpleTestCase):
    @override_settings(TWILIO_SMS_FROM="+15551234567", TWILIO_WHATSAPP_FROM="whatsapp:+14155238886")
    def test_sms_channel_takes_priority_when_configured(self):
        self.assertEqual(get_parent_message_channel(), "sms")
        self.assertEqual(get_parent_message_channel_label(), "SMS")

    @override_settings(TWILIO_SMS_FROM="", TWILIO_WHATSAPP_FROM="whatsapp:+14155238886")
    def test_whatsapp_channel_used_when_sms_is_not_configured(self):
        self.assertEqual(get_parent_message_channel(), "whatsapp")
        self.assertEqual(get_parent_message_channel_label(), "WhatsApp")
