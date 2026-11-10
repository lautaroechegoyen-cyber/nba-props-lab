"""Post-test diagnostics; descriptions only, never auto-modify the model."""
import numpy as np
import pandas as pd


def analyze(all_predictions: pd.DataFrame):
    """Return a bias table by prop and reliability bins from chronologically tested props."""
    if all_predictions.empty:
        return pd.DataFrame(),pd.DataFrame()
    x=all_predictions.loc[all_predictions['lado']=='OVER'].copy()
    if x.empty:
        return pd.DataFrame(),pd.DataFrame()
    x['error_real_menos_modelo']=x['real']-x['proyeccion']
    x['error_abs']=x['error_real_menos_modelo'].abs()
    group=(x.groupby('prop').agg(
        n=('real','size'),mae=('error_abs','mean'),
        sesgo_real_menos_modelo=('error_real_menos_modelo','mean'),
        prediccion_media=('proyeccion','mean'),real_media=('real','mean'))
           .reset_index().sort_values('n',ascending=False))
    v=x.loc[x['resultado']!='PUSH'].copy()
    if v.empty:
        return group,pd.DataFrame()
    v['grupo_prob']=pd.cut(v['probabilidad'],bins=np.linspace(0,1,11),
                           include_lowest=True)
    v['acierto']=v['resultado'].eq('WIN').astype(float)
    bins=(v.groupby('grupo_prob',observed=False).agg(
        n=('acierto','size'),prob_media=('probabilidad','mean'),
        frecuencia_real=('acierto','mean')).reset_index())
    bins['error_calibracion']=bins['frecuencia_real']-bins['prob_media']
    return group,bins
