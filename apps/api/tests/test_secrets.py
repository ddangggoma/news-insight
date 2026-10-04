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


def test_header_scheme_with_prefix() -> None:
    config = {
        "auth": {
            "secret": "KAKAO_REST_KEY",
            "scheme": "header",
            "header": "Authorization",
            "prefix": "KakaoAK ",
        }
    }

    headers = resolve_auth_headers(config, environ={"SOURCE_SECRET_KAKAO_REST_KEY": "k1"})

    assert headers == {"Authorization": "KakaoAK k1"}


def test_multiple_header_secrets() -> None:
    config = {
        "auth": {
            "scheme": "headers",
            "headers": {
                "X-Naver-Client-Id": "NAVER_CLIENT_ID",
                "X-Naver-Client-Secret": "NAVER_CLIENT_SECRET",
            },
        }
    }
    environ = {"SOURCE_SECRET_NAVER_CLIENT_ID": "id", "SOURCE_SECRET_NAVER_CLIENT_SECRET": "pw"}

    assert resolve_auth_headers(config, environ=environ) == {
        "X-Naver-Client-Id": "id",
        "X-Naver-Client-Secret": "pw",
    }
    with pytest.raises(SecretError, match="SOURCE_SECRET_NAVER_CLIENT_SECRET"):
        resolve_auth_headers(config, environ={"SOURCE_SECRET_NAVER_CLIENT_ID": "id"})
    with pytest.raises(SecretError, match="must map"):
        resolve_auth_headers({"auth": {"scheme": "headers"}}, environ=environ)
