import pytest

from coach import config


def test_profile_fills_what_the_environment_leaves_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOAL_LABEL", "")
    monkeypatch.delenv("ATHLETE_HR_MAX", raising=False)
    monkeypatch.setenv("GOAL_TIME_A", "39:30")
    config.save_profile({"GOAL_LABEL": "Semi", "ATHLETE_HR_MAX": "196", "GOAL_TIME_A": "1:25:00",
                         "GOAL_TIME_B": "1:29:00"})
    s = config.Settings()
    assert s.goal_label == "Semi" and s.hr_max == 196
    assert s.goal_a == 39 * 60 + 30  # the environment wins
    assert s.goal_b == 5340
    config.save_profile({"ATHLETE_HR_MAX": ""})
    assert config.Settings().hr_max is None


@pytest.mark.parametrize("bad", [{"GOAL_TIME_A": "vite"}, {"GOAL_DATE": "13/12"}, {"COROS_REGION": "mars"}, {"X": "1"}])
def test_profile_rejects_bad_values(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        config.save_profile(bad)


def test_secrets_come_from_the_vault_when_not_in_env(monkeypatch):
    from coach import vault
    monkeypatch.delenv("COROS_EMAIL", raising=False)
    vault.use(vault.MemoryBackend({"coros_email": "me@x.fr"}))
    try:
        assert config.Settings().coros_email == "me@x.fr"
    finally:
        vault.use(vault.NoBackend())
