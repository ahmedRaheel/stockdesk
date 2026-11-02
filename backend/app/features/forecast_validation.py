"""Leakage-free rolling-origin demand forecasts for sparse daily retail quantities.

Uses daily mean or matching-weekday mean, selecting the lower backtest WAPE.
No external ML service and no misleading confidence claims.
"""
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean


def predict(history: list[tuple[date,float]], target: date, method: str) -> float:
    if not history:
        return 0.0
    sample=history[-84:]
    if method == 'weekday':
        matched=[q for d,q in sample if d.weekday()==target.weekday()]
        if len(matched)>=3:
            return max(0.0,mean(matched))
    return max(0.0,mean(q for _,q in sample))


def evaluate(history: list[tuple[date,float]], horizon: int = 14) -> dict:
    """Hold out last 14-28 days, never using a future observation for a prediction."""
    if horizon<1 or horizon>90:
        raise ValueError('Invalid forecast horizon')
    history=sorted(history)
    if len(history)<42:
        return {'method':'daily_mean','validation':'insufficient_history',
                'wape':None,'predicted_units':round(sum(predict(history,history[-1][0]+timedelta(days=i+1),'daily_mean') for i in range(horizon)),3) if history else 0}
    window=min(28,max(14,len(history)//5))
    scores={}
    for method in ('daily_mean','weekday'):
        error=0.0;actual=0.0
        for index in range(len(history)-window,len(history)):
            expected=predict(history[:index],history[index][0],method)
            quantity=history[index][1]
            error+=abs(quantity-expected)
            actual+=quantity
        scores[method]=round(error/actual,4) if actual>0 else (0.0 if error==0 else None)
    candidates={k:v for k,v in scores.items() if v is not None}
    chosen=min(candidates,key=candidates.get) if candidates else 'daily_mean'
    begin=history[-1][0]
    units=sum(predict(history,begin+timedelta(days=i),chosen) for i in range(1,horizon+1))
    return {'method':chosen,'validation':'rolling_origin','wape':scores[chosen],
            'predicted_units':round(units,3), 'holdout_days':window,
            'candidate_wape':scores}
