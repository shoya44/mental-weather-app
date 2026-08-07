import os
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

JST = timezone(timedelta(hours=9))

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def save_and_predict(cond_val, melan_val, env_data):
    cond_val = int(cond_val)
    melan_val = int(melan_val)
    
    # ベースの加減算計算
    base_pred = cond_val + env_data['adj']['total']
    pred_val = max(0, min(9, base_pred))
    match_count = 0
    
    try:
        supabase = get_supabase_client()
        response = supabase.table('logs').select('*').execute()
        records = response.data or []
        
        records_dict = {r['date']: r for r in records}
        next_day_conds = []
        
        # 類似データの判定
        for r in records:
            if r.get('cond') == cond_val and r.get('env'):
                past_adj = r['env'].get('adj', {})
                curr_adj = env_data['adj']
                
                if (past_adj.get('melan') == curr_adj['melan'] and
                    past_adj.get('wx') == curr_adj['wx'] and
                    past_adj.get('temp') == curr_adj['temp'] and
                    past_adj.get('humid') == curr_adj['humid'] and
                    past_adj.get('pres') == curr_adj['pres']):
                    
                    past_date = datetime.strptime(r['date'], "%Y-%m-%d").date()
                    next_date_str = (past_date + timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    if next_date_str in records_dict:
                        next_day_conds.append(records_dict[next_date_str]['cond'])
                        
        if next_day_conds:
            match_count = len(next_day_conds)
            avg_cond = sum(next_day_conds) / match_count
            pred_val = max(0, min(9, int(round(avg_cond))))
            
        # 今日の日付でデータ保存 (Upsert)
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        data_to_save = {
            "date": today_str,
            "cond": cond_val,
            "melan": melan_val,
            "pred": pred_val,
            "env": env_data
        }
        supabase.table('logs').upsert(data_to_save).execute()

    except Exception as e:
        print(f"Supabase DB Error (Fallback to basic calculation): {e}")
        # DB接続エラー時はフォールバック計算値をそのまま採用する
        
    return pred_val, match_count
