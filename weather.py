import os
import requests
from datetime import datetime, timedelta

# 天気データ取得関数
def get_weather_and_calc_adj(melan_val):
    api_key = os.environ.get('OPENWEATHER_API_KEY')
    # 東京の緯度経度（お住まいの地域に合わせて変更可能です）
    lat, lon = 35.6895, 139.6917
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    
    res = requests.get(url)
    data = res.json()
    
    # 日本時間（UTC+9）での今日と明日の日付文字列を作成
    now_jst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_jst.strftime("%Y-%m-%d")
    tomorrow_str = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_temps, today_pres = [], []
    tom_temps, tom_pres, tom_humid, tom_wx = [], [], [], []
    
    # APIのリスト(3時間ごとのデータ)から今日と明日のデータを振り分け
    for item in data['list']:
        dt_jst = datetime.utcfromtimestamp(item['dt']) + timedelta(hours=9)
        date_str = dt_jst.strftime("%Y-%m-%d")
        
        if date_str == today_str:
            today_temps.append(item['main']['temp'])
            today_pres.append(item['main']['pressure'])
        elif date_str == tomorrow_str:
            tom_temps.append(item['main']['temp'])
            tom_pres.append(item['main']['pressure'])
            tom_humid.append(item['main']['humidity'])
            tom_wx.append(item['weather'][0]['main'])

    # 今日のデータがない時間帯（深夜など）のフォールバック
    if not today_temps: today_temps = tom_temps
    if not today_pres: today_pres = tom_pres

    # 必要な各数値を抽出
    t_max_tom = max(tom_temps)
    p_min_tom = min(tom_pres)
    h_max_tom = max(tom_humid)
    diff_t = round(abs(t_max_tom - max(today_temps)), 1)
    diff_p = round(p_min_tom - min(today_pres), 1)

    # 明日の天気の判定（雨などの悪天候を優先して抽出）
    wx_priority = {"Thunderstorm": -1, "Drizzle": -1, "Rain": -1, "Snow": -1, "Clouds": 0, "Clear": 1}
    best_wx, wx_pt = "Clear", 1
    for w in tom_wx:
        val = wx_priority.get(w, 0)
        if val < wx_pt:
            wx_pt, best_wx = val, w

    # --- 補正ポイントの計算 ---
    melan_pt = -int(melan_val)
    
    if diff_t >= 7: temp_pt = -2
    elif diff_t >= 4: temp_pt = -1
    else: temp_pt = 0
    
    humid_pt = 0 if 40 <= h_max_tom <= 60 else -1
    
    if diff_p <= -6: pres_pt = -2
    elif diff_p <= -3: pres_pt = -1
    else: pres_pt = 0
    
    total_adj = melan_pt + wx_pt + temp_pt + humid_pt + pres_pt

    # DBに保存するenvの形（JSONB）でデータをまとめる
    env_data = {
        "fcst": {"wx": best_wx, "t_max": t_max_tom, "h_max": h_max_tom, "p_min": p_min_tom},
        "diff": {"t_max": diff_t, "p_min": diff_p},
        "adj": {"melan": melan_pt, "wx": wx_pt, "temp": temp_pt, "humid": humid_pt, "pres": pres_pt, "total": total_adj}
    }
    
    return env_data