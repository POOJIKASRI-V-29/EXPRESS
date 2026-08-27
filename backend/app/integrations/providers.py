"""Provider registry.

Each entry carries the real OAuth endpoints. A provider is only *offerable*
when the server actually holds its client credentials — `configured()` is what
keeps the Integrations page honest rather than showing buttons that cannot work.
"""
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    icon: str
    blurb: str
    scopes: tuple[str, ...]
    authorize_url: str
    token_url: str
    client_id_setting: str
    client_secret_setting: str
    # Extra params some providers require on the authorize request.
    extra_authorize: dict = field(default_factory=dict)

    @property
    def client_id(self) -> str | None:
        return getattr(settings, self.client_id_setting, None)

    @property
    def client_secret(self) -> str | None:
        return getattr(settings, self.client_secret_setting, None)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def missing(self) -> str:
        absent = [s for s in (self.client_id_setting, self.client_secret_setting)
                  if not getattr(settings, s, None)]
        return " and ".join(absent)

    def redirect_uri(self) -> str:
        return f"{settings.OAUTH_REDIRECT_BASE.rstrip('/')}/integrations/{self.name}/callback"


PROVIDERS: dict[str, Provider] = {
    "calendar": Provider(
        name="calendar", label="Google Calendar", icon="cal",
        blurb="Two-way sync for classes, exams and scheduled tasks.",
        scopes=("https://www.googleapis.com/auth/calendar.events",),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id_setting="GOOGLE_CLIENT_ID", client_secret_setting="GOOGLE_CLIENT_SECRET",
        # offline+consent is what actually yields a refresh token from Google.
        extra_authorize={"access_type": "offline", "prompt": "consent"},
    ),
    "email": Provider(
        name="email", label="Gmail", icon="mail",
        blurb="Read-only scan for deadlines and result announcements.",
        scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id_setting="GOOGLE_CLIENT_ID", client_secret_setting="GOOGLE_CLIENT_SECRET",
        extra_authorize={"access_type": "offline", "prompt": "consent"},
    ),
    "github": Provider(
        name="github", label="GitHub", icon="projects",
        blurb="Commit counts and issue sync for Projects.",
        scopes=("repo:status", "read:user"),
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        client_id_setting="GITHUB_CLIENT_ID", client_secret_setting="GITHUB_CLIENT_SECRET",
    ),
    "drive": Provider(
        name="drive", label="Google Drive", icon="learning",
        blurb="Attach lecture material and submissions to courses.",
        scopes=("https://www.googleapis.com/auth/drive.file",),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id_setting="GOOGLE_CLIENT_ID", client_secret_setting="GOOGLE_CLIENT_SECRET",
        extra_authorize={"access_type": "offline", "prompt": "consent"},
    ),
}


def get(name: str) -> Provider | None:
    return PROVIDERS.get(name)
