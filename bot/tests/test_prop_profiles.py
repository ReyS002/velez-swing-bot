from bot.core.prop_manager import PropProfileManager


class Risk:
    prop_config = {"max_trailing_drawdown": 999, "max_open_positions": 1}


def test_legacy_profiles_are_review_only_and_cannot_recalibrate_risk():
    manager = PropProfileManager()
    profile = manager.get_active_profile()
    before = dict(Risk.prop_config)
    manager.apply_to_risk_manager(Risk())
    assert profile["status"] == "review_required"
    assert profile["submit_eligible"] is False
    assert Risk.prop_config == before
