import numpy as np
import pytest
from ppk2_cmd.analysis import MeasurementResult


def test_measurement_result_stats():
    # 2 seconds of 100k samples/sec = 200k samples
    # Sec 1: 10 mA (10,000 uA), Sec 2: 20 mA (20,000 uA)
    s1 = np.full(100_000, 10_000.0)
    s2 = np.full(100_000, 20_000.0)
    current_ua = np.concatenate([s1, s2])
    current_ma = current_ua / 1000.0
    t = np.linspace(0, 2.0, len(current_ua), endpoint=False)

    res = MeasurementResult(
        timestamps_s=t,
        current_ua=current_ua,
        current_ma=current_ma,
        voltage_mv=5000,
        duration_s=2.0,
        sample_rate_sps=100_000.0,
        mean_ua=float(np.mean(current_ua)),
        min_ua=float(np.min(current_ua)),
        max_ua=float(np.max(current_ua)),
        std_ua=float(np.std(current_ua)),
        avg_power_mw=(float(np.mean(current_ua)) / 1000.0) * 5.0
    )

    per_sec = res.get_per_second_stats()
    assert len(per_sec) == 2
    assert per_sec[0].second == 1
    assert pytest.approx(per_sec[0].mean_ma, 0.01) == 10.0
    assert pytest.approx(per_sec[0].power_mw, 0.01) == 50.0

    assert per_sec[1].second == 2
    assert pytest.approx(per_sec[1].mean_ma, 0.01) == 20.0
    assert pytest.approx(per_sec[1].power_mw, 0.01) == 100.0

    assert pytest.approx(res.avg_power_mw, 0.01) == 75.0
