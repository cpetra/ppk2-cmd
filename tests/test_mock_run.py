import os
import tempfile
from ppk2_cmd.core import measure


def test_mock_measurement_and_exports():
    res = measure(voltage_mv=5000, duration_s=1.0, mock=True)
    assert res is not None
    assert len(res.current_ua) == 100_000
    assert res.voltage_mv == 5000
    assert res.duration_s == 1.0
    assert res.mean_ua > 0

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = os.path.join(tmpdir, "test.csv")
        npz_file = os.path.join(tmpdir, "test.npz")
        json_file = os.path.join(tmpdir, "test.json")
        png_file = os.path.join(tmpdir, "test.png")

        res.save_csv(csv_file)
        assert os.path.exists(csv_file)
        assert os.path.getsize(csv_file) > 0

        res.save_npz(npz_file)
        assert os.path.exists(npz_file)
        assert os.path.getsize(npz_file) > 0

        res.save_json(json_file)
        assert os.path.exists(json_file)
        assert os.path.getsize(json_file) > 0

        res.plot(png_file)
        assert os.path.exists(png_file)
        assert os.path.getsize(png_file) > 0
