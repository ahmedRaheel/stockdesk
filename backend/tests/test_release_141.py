"""Standalone deterministic forecasting checks; database integration requires Docker."""
from datetime import date,timedelta
from app.features.forecast_validation import predict,evaluate


def test_forecast_weekday_rolling_origin():
    begin=date(2026,1,1)
    history=[(begin+timedelta(days=i),float(10 if i%7==0 else 2)) for i in range(90)]
    report=evaluate(history,14)
    assert report['validation']=='rolling_origin'
    assert report['method'] in ('daily_mean','weekday')
    assert 0 <= report['wape'] <= 1
    assert report['predicted_units']>=0


def test_no_future_observations_in_predict():
    begin=date(2026,1,1)
    history=[(begin+timedelta(days=i),3.0) for i in range(60)]
    future=(begin+timedelta(days=60),100000.0)
    target=begin+timedelta(days=61)
    assert predict(history,target,'weekday') == 3.0
    assert predict(history,target,'daily_mean') == 3.0
    assert evaluate(history,14)['predicted_units']==42
    assert future[1] > 3


def test_sparse_forecasting_not_claiming_validated():
    assert evaluate([],7)['validation']=='insufficient_history'
    assert evaluate([(date(2026,1,1),0)],7)['predicted_units']==0


def test_forecast_horizon_boundary():
    try:
        evaluate([],91)
    except ValueError:
        pass
    else:
        assert False
