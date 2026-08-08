import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import io
import time
from db import get_supabase_client
import urllib.request
import os

def get_japanese_font():
    font_path = '/tmp/NotoSansJP-Regular.otf'
    if not os.path.exists(font_path):
        url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"
        urllib.request.urlretrieve(url, font_path)
    return FontProperties(fname=font_path)

# JSON(env)から気象データを取り出して整形するヘルパー関数
def parse_env(row):
    env = row['env'] if 'env' in row else None
    if not isinstance(env, dict):
        return pd.Series(['-', '-', '-', '-', '-'])
    
    fcst = env.get('fcst', {})
    diff = env.get('diff', {})
    adj = env.get('adj', {})
    
    # 絵文字を除去して文字化けを防ぐ
    wx = fcst.get('wx_jp', '-').replace('☀️','').replace('🌤️','').replace('☁️','').replace('☔','').replace('⛈️','').replace('⚡','').replace('❄️','')
    
    t_max = fcst.get('t_max', '-')
    t_diff = diff.get('t_max', 0)
    t_str = f"{t_max}℃ ({t_diff:+}℃)" if t_max != '-' else '-'
    
    h_max = fcst.get('h_max', '-')
    h_str = f"{h_max}%" if h_max != '-' else '-'
    
    p_min = fcst.get('p_min', '-')
    p_diff = diff.get('p_min', 0)
    p_str = f"{p_min}hPa ({p_diff:+}hPa)" if p_min != '-' else '-'
    
    adj_total = adj.get('total', '-')
    adj_str = f"{adj_total:+}Pt" if isinstance(adj_total, int) else '-'
    
    return pd.Series([wx, t_str, h_str, p_str, adj_str])

def generate_and_upload_reports():
    supabase = get_supabase_client()
    fp = get_japanese_font() 
    
    response = supabase.table('logs').select('*').order('date').execute()
    records = response.data

    if not records:
        return None, None

    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.tail(7)
    
    df.index = df.index.strftime('%m/%d')

    # ----- ① グラフ画像の作成 -----
    plt.figure(figsize=(10, 6))
    
    plt.plot(df.index, df['cond'], label='実績', marker='o', color='darkorange', linewidth=2)
    plt.plot(df.index, df['pred'], label='予報', marker='x', color='royalblue', linestyle='--')
    plt.bar(df.index, df['melan'], label='憂鬱', color='gray', alpha=0.3, width=0.5)

    plt.title('直近7日間の推移', fontproperties=fp, fontsize=16)
    plt.ylim(0, 10)
    plt.yticks(range(11))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    plt.legend(loc='upper left', prop=fp)
    plt.tight_layout()

    graph_buf = io.BytesIO()
    plt.savefig(graph_buf, format='png', dpi=100)
    graph_buf.seek(0)
    plt.close()

    # ----- ② エクセル風の表画像の作成 (情報増量版) -----
    table_df = pd.DataFrame(index=df.index)
    table_df['調子'] = df['cond']
    table_df['憂鬱'] = df['melan']
    
    # 新しいデータ列を追加
    table_df[['天気', '最高気温', '湿度', '最低気圧', '環境Pt']] = df.apply(parse_env, axis=1)
    table_df['予報'] = df['pred']
    
    # テーブルが横に長くなるため、画像の横幅を拡張 (6 -> 12)
    fig, ax = plt.subplots(figsize=(12, 4)) 
    ax.axis('off')
    
    table = ax.table(cellText=table_df.values,
                     rowLabels=table_df.index,
                     colLabels=table_df.columns,
                     cellLoc='center',
                     loc='center')
    
    # セルの余白と文字サイズを調整
    table.scale(1, 1.8)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=fp)
        
    table_buf = io.BytesIO()
    # 文字をくっきりさせるためにDPIを120に設定
    plt.savefig(table_buf, format='png', dpi=120, bbox_inches='tight')
    table_buf.seek(0)
    plt.close()

    # ----- ③ Supabase Storage へアップロード -----
    timestamp = int(time.time())
    graph_filename = f"graph_{timestamp}.png"
    table_filename = f"table_{timestamp}.png"

    supabase.storage.from_("reports").upload(
        path=graph_filename,
        file=graph_buf.read(),
        file_options={"content-type": "image/png"}
    )
    supabase.storage.from_("reports").upload(
        path=table_filename,
        file=table_buf.read(),
        file_options={"content-type": "image/png"}
    )

    graph_url = supabase.storage.from_("reports").get_public_url(graph_filename)
    table_url = supabase.storage.from_("reports").get_public_url(table_filename)

    return graph_url, table_url
