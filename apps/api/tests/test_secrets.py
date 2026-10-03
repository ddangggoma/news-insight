import pytest

from news_insight.secrets import SecretError, resolve_auth_headers


def test_no_auth_means_no_headers() -> None:
    assert resolve_auth_headers({}, environ={}) == {}


def test_bearer_token_from_prefixed_variable() -> None:
    headers = resolve_auth_headers(
        {"auth": {"secret": "GITHUB_TOKEN"}}, environ={"SOURCE_SECRET_GITHUB_TOKEN": "t0k"}
    )

    assert headers == {"Authorization": "Bearer t0k"}


def test_custom_header_scheme() -> None:
    config = {"auth": {"scheme": "header", "header": "X-Api-Key", "secret": "YOUTUBE_KEY"}}

    assert resolve_auth_headers(config, environ={"SOURCE_SECRET_YOUTUBE_KEY": "k"}) == {
        "X-Api-Key": "k"
    }


def test_missing_secret_is_reported_without_a_value() -> None:
    with pytest.raises(SecretError, match="SOURCE_SECRET_GITHUB_TOKEN is not configured"):
        resolve_auth_headers({"auth": {"secret": "GITHUB_TOKEN"}}, environ={})


def test_secret_names_cannot_reach_other_variables() -> None:
    with pytest.raises(SecretError, match="invalid secret name"):
        resolve_auth_headers({"auth": {"secret": "postgres_password"}}, environ={})
    with pytest.raises(SecretError, match="not configured"):
        resolve_auth_headers(
            {"auth": {"secret": "POSTGRES_PASSWORD"}}, environ={"POSTGRES_PASSWORD": "db"}
        )


def test_unsupported_scheme_is_rejected() -> None:
    config = {"auth": {"scheme": "basic", "secret": "TOKEN"}}

    with pytest.raises(SecretError, match="unsupported auth scheme"):
        resolve_auth_headers(config, environ={"SOURCE_SECRET_TOKEN": "x"})
