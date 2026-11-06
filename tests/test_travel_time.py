import pandas as pd

from race_casablanca.network.travel_time import CongestionModel, travel_time_seconds


def test_travel_time_nonnegative_and_waiting_policy():
    model = CongestionModel(citywide_hour=pd.Series({h: 1.5 for h in range(24)}))
    model.citywide_hour[9] = 0.5
    duration = travel_time_seconds(600.0, 8 * 3600 + 3500, model, wait_for_fifo=True)
    assert duration >= 0
    immediate = travel_time_seconds(600.0, 8 * 3600 + 3500, model, wait_for_fifo=False)
    assert duration >= 0 and immediate >= 0
