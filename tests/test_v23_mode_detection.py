from src.contracts.v23_multi_mode_analysis import detect_game_mode, METRIC_APPLICABILITY_PRESETS


def test_detect_game_mode_mapping():
    assert detect_game_mode(450).mode == "ARAM"
    assert detect_game_mode(1700).mode == "Arena"
    assert detect_game_mode(420).mode == "SR"
    # Unknown queues fall back
    assert detect_game_mode(9999).mode == "Fallback"


def test_metric_applicability_matrix():
    aram = METRIC_APPLICABILITY_PRESETS["ARAM"]
    assert aram.vision_enabled is False
    assert aram.objective_control_enabled is False
    assert aram.combat_weight > 1.0

    arena = METRIC_APPLICABILITY_PRESETS["Arena"]
    assert arena.economy_enabled is False
    assert arena.objective_control_enabled is False
    assert arena.vision_enabled is False
