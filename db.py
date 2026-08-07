import os
from datetime import datetime, timedelta
from supabase import create_client, Client

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def save_and_predict(cond_val, melan_val, env_data):
    supabase = get_supabase_client()
    cond_val = int(cond_val)
    melan_val = int(melan_val)
    
    # ① デフォルトの計算（過去に類似データがない場合のベース点）
    base_pred = cond_val + env_data['adj']['total']
    pred_val = max(0, min(9, base_pred)) # 0〜9の範囲に収める
    
    # ② 過去データの取得
    response = supabase.table('logs').select('*').execute()
    records = response.data
    
    # 日付で検索しやすくするための辞書
    records_dict = {r['date']: r for r in records}
    next_day_conds = []
    
    # ③ 類似データの検索（調子と補正Ptが完全一致する日を探す）
    for r in records:
        if r.get('cond') == cond_val and r.get('env'):
            past_adj = r['env'].get('adj', {})
            curr_adj = env_data['adj']
            
            # すべての補正値が一致しているか判定
            if (past_adj.get('melan') == curr_adj['melan'] and
                past_adj.get('wx') == curr_adj['wx'] and
                past_adj.get('temp') == curr_adj['temp'] and
                past_adj.get('humid') == curr_adj['humid'] and
                past_adj.get('pres') == curr_adj['pres']):
                
                # 一致した日の「翌日の日付」を計算
                past_date = datetime.strptime(r['date'], "%Y-%m-%d").date()
                next_date = past_date + timedelta(days=1)
                next_date_str = next_date.strftime("%Y-%m-%d")
                
                # その翌日の実績（cond）が記録されていればリストに追加
                if next_date_str in records_dict:
                    next_day_conds.append(records_dict[next_date_str]['cond'])
                    
    # ④ 類似実績があれば平均値を予報Ptにする
    if next_day_conds:
        avg_cond = sum(next_day_conds) / len(next_day_conds)
        pred_val = max(0, min(9, int(round(avg_cond))))
        
    # ⑤ Supabaseに今日のデータを保存（Upsert: あれば上書き、なければ新規）
    now_jst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_jst.strftime("%Y-%m-%d")
    
    data_to_save = {
        "date": today_str,
        "cond": cond_val,
        "melan": melan_val,
        "pred": pred_val,
        "env": env_data
    }
    
    supabase.table('logs').upsert(data_to_save).execute()
    
    return pred_val, len(next_day_conds)