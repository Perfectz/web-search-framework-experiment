from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from apartment_agent.utils import ensure_parent


SMTP_ENV_DEFAULTS = {
    "APARTMENT_AGENT_SMTP_HOST": "smtp.gmail.com",
    "APARTMENT_AGENT_SMTP_PORT": "587",
    "APARTMENT_AGENT_SMTP_USERNAME": "pzgambo@gmail.com",
    "APARTMENT_AGENT_SMTP_PASSWORD": "",
    "APARTMENT_AGENT_SMTP_FROM": "pzgambo@gmail.com",
    "APARTMENT_AGENT_SMTP_FROM_NAME": "Patrick",
    "APARTMENT_AGENT_SMTP_REPLY_TO": "pzgambo@gmail.com",
    "APARTMENT_AGENT_SMTP_USE_TLS": "1",
}


@dataclass(slots=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str = ""
    reply_to: str = ""
    use_tls: bool = True

    @property
    def from_header(self) -> str:
        if self.from_name.strip():
            return formataddr((self.from_name.strip(), self.from_email.strip()))
        return self.from_email.strip()


class SMTPConfigurationError(RuntimeError):
    pass


def load_env_file(env_path: str | Path = ".env") -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def apply_env_overrides(env_path: str | Path = ".env") -> dict[str, str]:
    values = load_env_file(env_path)
    for key, value in values.items():
        os.environ[key] = value
    return values


def get_smtp_env_values(env_path: str | Path = ".env") -> dict[str, str]:
    values = dict(SMTP_ENV_DEFAULTS)
    values.update(load_env_file(env_path))
    for key in SMTP_ENV_DEFAULTS:
        current = os.getenv(key)
        if current is not None:
            values[key] = current
    return values


def save_smtp_env_values(values: dict[str, str], env_path: str | Path = ".env") -> Path:
    merged = dict(SMTP_ENV_DEFAULTS)
    merged.update({key: str(value) for key, value in values.items()})
    path = ensure_parent(env_path)
    lines = [
        "# Local SMTP settings for Apartment Agent.",
        "# Keep this file out of source control.",
        "",
    ]
    for key in SMTP_ENV_DEFAULTS:
        lines.append(f"{key}={_format_env_value(merged.get(key, ''))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    apply_env_overrides(path)
    return path


def load_smtp_settings_from_env(env_path: str | Path = ".env") -> SMTPSettings:
    apply_env_overrides(env_path)
    host = os.getenv("APARTMENT_AGENT_SMTP_HOST", "").strip()
    port_text = os.getenv("APARTMENT_AGENT_SMTP_PORT", "587").strip()
    username = os.getenv("APARTMENT_AGENT_SMTP_USERNAME", "").strip()
    password = os.getenv("APARTMENT_AGENT_SMTP_PASSWORD", "").strip()
    from_email = os.getenv("APARTMENT_AGENT_SMTP_FROM", "").strip()
    from_name = os.getenv("APARTMENT_AGENT_SMTP_FROM_NAME", "").strip()
    reply_to = os.getenv("APARTMENT_AGENT_SMTP_REPLY_TO", "").strip()
    use_tls = os.getenv("APARTMENT_AGENT_SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"}

    missing = [
        name
        for name, value in [
            ("APARTMENT_AGENT_SMTP_HOST", host),
            ("APARTMENT_AGENT_SMTP_USERNAME", username),
            ("APARTMENT_AGENT_SMTP_PASSWORD", password),
            ("APARTMENT_AGENT_SMTP_FROM", from_email),
        ]
        if not value
    ]
    if missing:
        raise SMTPConfigurationError("Missing SMTP settings: " + ", ".join(missing))

    try:
        port = int(port_text)
    except ValueError as exc:
        raise SMTPConfigurationError("APARTMENT_AGENT_SMTP_PORT must be an integer.") from exc

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        use_tls=use_tls,
    )


def send_email(settings: SMTPSettings, to: str, subject: str, body: str) -> None:
    recipient = to.strip()
    if not recipient:
        raise ValueError("Recipient email is required.")

    message = EmailMessage()
    message["From"] = settings.from_header
    message["To"] = recipient
    message["Subject"] = subject.strip()
    if settings.reply_to.strip():
        message["Reply-To"] = settings.reply_to.strip()
    message.set_content(body)

    with smtplib.SMTP(settings.host, settings.port, timeout=30) as smtp:
        smtp.ehlo()
        if settings.use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.username, settings.password)
        smtp.send_message(message)


def test_smtp_connection(settings: SMTPSettings) -> None:
    with smtplib.SMTP(settings.host, settings.port, timeout=30) as smtp:
        smtp.ehlo()
        if settings.use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.username, settings.password)


def _format_env_value(value: str) -> str:
    text = str(value)
    if text == "":
        return ""
    if any(character in text for character in [' ', '#', '"', "'", '=']):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text
