"""Settings come from the environment and .env; models are never read from code paths."""

from kyc_workflow.config import Settings


def test_models_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("KYC_MODEL", "bank-main-model")
    monkeypatch.setenv("KYC_GUARD_MODEL", "bank-small-model")
    monkeypatch.setenv("KYC_EVAL_MODEL", "bank-eval-model")
    monkeypatch.delenv("KYC_MODEL_ALLOWLIST", raising=False)

    s = Settings.from_env()

    assert (s.model, s.guard_model, s.eval_model) == ("bank-main-model", "bank-small-model", "bank-eval-model")
    assert set(s.model_allowlist) == {"bank-main-model", "bank-small-model", "bank-eval-model"}


def test_explicit_allowlist_is_kept_and_configured_models_added(monkeypatch):
    monkeypatch.setenv("KYC_MODEL", "m1")
    monkeypatch.setenv("KYC_GUARD_MODEL", "m2")
    monkeypatch.setenv("KYC_EVAL_MODEL", "m2")
    monkeypatch.setenv("KYC_MODEL_ALLOWLIST", "m9, m1")

    s = Settings.from_env()

    assert s.model_allowlist == ("m9", "m1", "m2")


def test_with_model_keeps_the_other_models(monkeypatch):
    monkeypatch.setenv("KYC_MODEL", "m1")
    monkeypatch.setenv("KYC_GUARD_MODEL", "m2")
    monkeypatch.setenv("KYC_EVAL_MODEL", "m3")
    s = Settings.from_env().with_model("m4")
    assert s.model == "m4" and s.guard_model == "m2" and s.eval_model == "m3"
    assert "m4" in s.model_allowlist and "m1" in s.model_allowlist
