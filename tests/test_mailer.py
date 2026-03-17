import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apartment_agent.mailer import (
    SMTPConfigurationError,
    SMTPSettings,
    apply_env_overrides,
    get_smtp_env_values,
    load_smtp_settings_from_env,
    save_smtp_env_values,
    send_email,
    test_smtp_connection,
)


class MailerTests(unittest.TestCase):
    def test_load_smtp_settings_from_env_reads_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APARTMENT_AGENT_SMTP_HOST": "smtp.example.com",
                "APARTMENT_AGENT_SMTP_PORT": "2525",
                "APARTMENT_AGENT_SMTP_USERNAME": "patrick",
                "APARTMENT_AGENT_SMTP_PASSWORD": "secret",
                "APARTMENT_AGENT_SMTP_FROM": "patrick@example.com",
                "APARTMENT_AGENT_SMTP_FROM_NAME": "Patrick",
                "APARTMENT_AGENT_SMTP_REPLY_TO": "reply@example.com",
                "APARTMENT_AGENT_SMTP_USE_TLS": "0",
            },
            clear=True,
        ):
            settings = load_smtp_settings_from_env(env_path="missing.env")

        self.assertEqual(settings.host, "smtp.example.com")
        self.assertEqual(settings.port, 2525)
        self.assertEqual(settings.username, "patrick")
        self.assertEqual(settings.password, "secret")
        self.assertEqual(settings.from_email, "patrick@example.com")
        self.assertEqual(settings.from_name, "Patrick")
        self.assertEqual(settings.reply_to, "reply@example.com")
        self.assertFalse(settings.use_tls)

    def test_load_smtp_settings_from_env_raises_on_missing_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SMTPConfigurationError) as error:
                load_smtp_settings_from_env(env_path="missing.env")

        self.assertIn("APARTMENT_AGENT_SMTP_HOST", str(error.exception))
        self.assertIn("APARTMENT_AGENT_SMTP_USERNAME", str(error.exception))
        self.assertIn("APARTMENT_AGENT_SMTP_PASSWORD", str(error.exception))
        self.assertIn("APARTMENT_AGENT_SMTP_FROM", str(error.exception))

    @patch("apartment_agent.mailer.smtplib.SMTP")
    def test_send_email_uses_tls_login_and_send(self, smtp_cls) -> None:
        smtp = smtp_cls.return_value.__enter__.return_value
        settings = SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="patrick",
            password="secret",
            from_email="patrick@example.com",
            from_name="Patrick",
            reply_to="reply@example.com",
            use_tls=True,
        )

        send_email(settings, "agent@example.com", "Subject line", "Body text")

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        smtp.ehlo.assert_called()
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("patrick", "secret")
        smtp.send_message.assert_called_once()

        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "Patrick <patrick@example.com>")
        self.assertEqual(message["To"], "agent@example.com")
        self.assertEqual(message["Subject"], "Subject line")
        self.assertEqual(message["Reply-To"], "reply@example.com")
        self.assertEqual(message.get_content().strip(), "Body text")

    @patch("apartment_agent.mailer.smtplib.SMTP")
    def test_test_smtp_connection_logs_in(self, smtp_cls) -> None:
        smtp = smtp_cls.return_value.__enter__.return_value
        settings = SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="patrick",
            password="secret",
            from_email="patrick@example.com",
            use_tls=True,
        )

        test_smtp_connection(settings)

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("patrick", "secret")

    def test_save_and_reload_smtp_env_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            save_smtp_env_values(
                {
                    "APARTMENT_AGENT_SMTP_USERNAME": "pzgambo@gmail.com",
                    "APARTMENT_AGENT_SMTP_PASSWORD": "app-password",
                    "APARTMENT_AGENT_SMTP_FROM_NAME": "Patrick",
                },
                env_path,
            )
            with patch.dict(os.environ, {}, clear=True):
                apply_env_overrides(env_path)
                values = get_smtp_env_values(env_path)

        self.assertEqual(values["APARTMENT_AGENT_SMTP_HOST"], "smtp.gmail.com")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_PORT"], "587")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_USERNAME"], "pzgambo@gmail.com")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_PASSWORD"], "app-password")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_FROM"], "pzgambo@gmail.com")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_FROM_NAME"], "Patrick")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_REPLY_TO"], "pzgambo@gmail.com")
        self.assertEqual(values["APARTMENT_AGENT_SMTP_USE_TLS"], "1")


if __name__ == "__main__":
    unittest.main()
