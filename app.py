import os
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

JST = timezone(timedelta(hours=9))

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def save_and_predict(cond_val, melan_val, memo_text, env_data):
    cond_val = int(cond_val)
    melan_val = int(melan_val)
    
    base_pred = cond_val + env_data['adj']['total']
    pred_val = max(0, min(9, base_pred))
    match_count = 0
    
    try:
        supabase = get_supabase_client()
        response = supabase.table('logs').select('*').execute()
        records = response.data or []
        
        records_dict = {r['date']: r for r in records}
        next_day_conds = []
        
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
            
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        data_to_save = {
            "date": today_str,
            "cond": cond_val,
            "melan": melan_val,
            "memo": memo_text,  # メモを追加
            "pred": pred_val,
            "env": env_data
        }
        supabase.table('logs').upsert(data_to_save).execute()

    except Exception as e:
        print(f"Supabase DB Error: {e}")
        
    return pred_val, match_count

# 直近7件のログを取得する関数
def get_recent_logs(limit=7):
    try:
        supabase = get_supabase_client()
        response = supabase.table('logs').select('*').order('date', desc=False).limit(limit).execute()
        return response.data or []
    except Exception as e:
        print(f"Error fetching recent logs: {e}")
        return []
