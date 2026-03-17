import unittest

from apartment_agent.gui import build_gmail_compose_url


class GuiTests(unittest.TestCase):
    def test_gmail_compose_url_includes_recipient_subject_and_body(self) -> None:
        url = build_gmail_compose_url(
            to="agent@example.com",
            subject="Test Subject",
            body="Line one\nLine two",
        )

        self.assertIn("https://mail.google.com/mail/?", url)
        self.assertIn("to=agent%40example.com", url)
        self.assertIn("su=Test+Subject", url)
        self.assertIn("body=Line+one%0ALine+two", url)


if __name__ == "__main__":
    unittest.main()
