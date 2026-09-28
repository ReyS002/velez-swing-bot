from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_native_healthcheck_for_standalone_swing_bot():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("healthcheck:") == 1
    assert compose.count("http://127.0.0.1:8080/health/live") == 1
    assert compose.count("start_period: 20s") == 1


def test_watch_only_is_explicit_in_every_environment_example():
    for relative in (".env.example", "bot/.env.example", "bot/deploy/env.example"):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "VELEZ_WATCH_ONLY=true" in content
        assert content.index("VELEZ_WATCH_ONLY=true") < content.index("VELEZ_EXECUTE_ORDERS=false")


def test_fastapi_lifecycle_uses_supported_lifespan_api():
    source = (ROOT / "bot/webhook_server.py").read_text(encoding="utf-8")

    assert 'lifespan=lifespan' in source
    assert '@app.on_event("startup")' not in source
    assert '@app.on_event("shutdown")' not in source


def test_runtime_sources_do_not_use_naive_utcnow():
    python_sources = list((ROOT / "bot").rglob("*.py"))
    offenders = [str(path.relative_to(ROOT)) for path in python_sources if ("datetime." + "utcnow()") in path.read_text(encoding="utf-8")]

    assert offenders == []
