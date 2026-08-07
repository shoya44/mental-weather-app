import os
import requests
from datetime import datetime, timedelta, timezone

# JST (日本標準時) のタイムゾーン定義
JST = timezone(timedelta(hours=9))

def get_weather_and_calc_adj(melan_val):
    api_key = os.environ.get('OPENWEATHER_API_KEY')
    lat, lon = 35.6895, 139.6917  # 東京の座標
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    
    # タイムアウトを10秒に設定して接続待ちで止まるのを防ぐ
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    
    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")
    tomorrow_str = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_temps, today_pres = [], []
    tom_temps, tom_pres, tom_humid, tom_wx = [], [], [], []
    
    for item in data['list']:
        # UTCタイムスタンプからJSTへ変換
        dt_jst = datetime.fromtimestamp(item['dt'], tz=timezone.utc).astimezone(JST)
        date_str = dt_jst.strftime("%Y-%m-%d")
        
        if date_str == today_str:
            today_temps.append(item['main']['temp'])
            today_pres.append(item['main']['pressure'])
        elif date_str == tomorrow_str:
            tom_temps.append(item['main']['temp'])
            tom_pres.append(item['main']['pressure'])
            tom_humid.append(item['main']['humidity'])
            tom_wx.append(item['weather'][0]['main'])

    # 今日のデータが既に過ぎている場合のフォールバック
    if not today_temps: today_temps = tom_temps
    if not today_pres: today_pres = tom_pres

    t_max_tom = round(max(tom_temps))
    p_min_tom = round(min(tom_pres))
    h_max_tom = round(max(tom_humid))
    
    diff_t_raw = round(t_max_tom - max(today_temps))
    diff_p_raw = round(p_min_tom - min(today_pres))

    # 悪天候を優先判定
    wx_priority = {"Thunderstorm": -1, "Drizzle": -1, "Rain": -1, "Snow": -1, "Clouds": 0, "Clear": 1}
    best_wx, wx_pt = "Clear", 1
    for w in tom_wx:
        val = wx_priority.get(w, 0)
        if val < wx_pt:
            wx_pt, best_wx = val, w

    wx_map = {
        "Clear": "晴れ☀️",
        "Clouds": "くもり☁️",
        "Rain": "雨☔",
        "Drizzle": "小雨☔",
        "Thunderstorm": "雷雨⚡",
        "Snow": "雪❄️"
    }
    wx_jp = wx_map.get(best_wx, "晴れ☀️")

    # ポイント計算
    melan_pt = -int(melan_val)
    
    abs_diff_t = abs(diff_t_raw)
    if abs_diff_t >= 7: temp_pt = -2
    elif abs_diff_t >= 4: temp_pt = -1
    else: temp_pt = 0
    
    humid_pt = 0 if 40 <= h_max_tom <= 60 else -1
    
    if diff_p_raw <= -6: pres_pt = -2
    elif diff_p_raw <= -3: pres_pt = -1
    else: pres_pt = 0
    
    total_adj = melan_pt + wx_pt + temp_pt + humid_pt + pres_pt

    def fmt_pt(pt):
        if pt > 0: return f"+{pt}Pt"
        elif pt == 0: return "±0Pt"
        else: return f"{pt}Pt"

    return {
        "fcst": {
            "wx": best_wx,
            "wx_jp": wx_jp,
            "t_max": t_max_tom,
            "h_max": h_max_tom,
            "p_min": p_min_tom
        },
        "diff": {
            "t_max": diff_t_raw,
            "p_min": diff_p_raw
        },
        "adj": {
            "melan": melan_pt, "wx": wx_pt, "temp": temp_pt, "humid": humid_pt, "pres": pres_pt,
            "total": total_adj
        },
        "fmt_pt": {
            "wx": fmt_pt(wx_pt),
            "temp": fmt_pt(temp_pt),
            "humid": fmt_pt(humid_pt),
            "pres": fmt_pt(pres_pt)
        }
    }
