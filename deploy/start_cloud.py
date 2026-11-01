"""Container startup: provision native OIDC TOML from an administrator secret."""

import os
from pathlib import Path
import tomllib


def start() -> None:
    configured = os.environ.get("STREAMLIT_AUTH_TOML")
    if configured:
        try:
            parsed = tomllib.loads(configured)
            if "auth" not in parsed:
                raise ValueError("Missing authentication settings.")
        except (tomllib.TOMLDecodeError, ValueError):
            raise SystemExit("STREAMLIT_AUTH_TOML is invalid; expected an [auth] section.") from None
        path = Path(".streamlit") / "secrets.toml"
        path.parent.mkdir(exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(configured)
    port = int(os.environ.get("PORT", "8000"))
    os.execvp("streamlit", [
        "streamlit", "run", "app.py", "--server.address=0.0.0.0",
        f"--server.port={port}", "--server.headless=true",
    ])


if __name__ == "__main__":
    start()
