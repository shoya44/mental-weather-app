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
    
    # グラフを描画する前に、日付を「8/7」のような形式に変換しておく
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

    # ----- ② エクセル風の表画像の作成 -----
    table_df = df[['cond', 'melan', 'pred']].copy()
    table_df.columns = ['調子', '憂鬱さ', '予報Pt']
    
    fig, ax = plt.subplots(figsize=(6, 3)) 
    ax.axis('off')
    
    table = ax.table(cellText=table_df.values,
                     rowLabels=table_df.index,
                     colLabels=table_df.columns,
                     cellLoc='center',
                     loc='center')
    
    table.scale(1, 1.5)
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=fp)
        
    table_buf = io.BytesIO()
    plt.savefig(table_buf, format='png', dpi=100, bbox_inches='tight')
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
