import httpx
import pytest
from openai import AuthenticationError, BadRequestError, RateLimitError

from utils import config, openai_client


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "DOTENV_FILE", tmp_path / "implementation" / ".env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Exclude unrelated ancestor configuration from these unit tests.
    monkeypatch.setattr(config, "dotenv_values", lambda path: {})
    return tmp_path


def test_dotenv_resolution_does_not_depend_on_import_order(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("OPENAI_API_KEY=dotenv-test-key\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOTENV_FILE", dotenv_file)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert openai_client.get_api_key() == "dotenv-test-key"


def test_dotenv_overrides_environment(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("OPENAI_API_KEY=dotenv-test-key\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOTENV_FILE", dotenv_file)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-test-key")

    assert openai_client.get_api_key() == "dotenv-test-key"
    assert config.os.environ["OPENAI_API_KEY"] == "environment-test-key"


def test_search_order_and_empty_values(isolated_config, monkeypatch):
    launch = isolated_config / "launch"
    launch.mkdir()
    monkeypatch.chdir(launch)
    values = {
        config.DOTENV_FILE: {"OPENAI_API_KEY": "implementation-key"},
        launch / ".env": {"OPENAI_API_KEY": "launch-key"},
        isolated_config / ".env": {"OPENAI_API_KEY": "parent-key"},
    }
    monkeypatch.setattr(config, "dotenv_values", lambda path: values.get(path, {}))
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")

    assert openai_client.get_api_key() == "implementation-key"
    values[config.DOTENV_FILE] = {"OPENAI_API_KEY": " "}
    assert openai_client.get_api_key() == "launch-key"
    values[launch / ".env"] = {}
    assert openai_client.get_api_key() == "parent-key"
    values.clear()
    assert openai_client.get_api_key() == "environment-key"


def test_missing_key_does_not_use_streamlit_secrets(isolated_config, monkeypatch):
    import streamlit as st

    class ForbiddenSecrets:
        def get(self, name):
            pytest.fail("Streamlit secrets must not be consulted.")

    monkeypatch.setattr(st, "secrets", ForbiddenSecrets())
    assert openai_client.get_api_key() is None
    with pytest.raises(openai_client.MissingAPIKeyError, match="OPENAI_API_KEY"):
        openai_client.get_client()


def test_client_uses_resolved_key_and_long_itinerary_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(openai_client, "resolve_secret", lambda name: ("test-key", ".env"))
    monkeypatch.setattr(openai_client, "OpenAI", lambda **kwargs: calls.append(kwargs))

    openai_client.get_client()

    assert calls == [{"api_key": "test-key", "timeout": 90.0, "max_retries": 1}]


@pytest.mark.parametrize(
    ("exception_type", "status", "expected"),
    [
        (AuthenticationError, 401, "valid OpenAI API key"),
        (RateLimitError, 429, "billing and quota"),
        (BadRequestError, 400, "request format"),
    ],
)
def test_provider_errors_are_actionable_and_do_not_expose_bodies(
    exception_type, status, expected
):
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    error = exception_type(
        "provider body contains a private key",
        response=response,
        body={"error": {"message": "private key"}},
    )

    message = openai_client.describe_openai_error(error)

    assert expected in message
    assert "private key" not in message

