import pandas as pd
import matplotlib.pyplot as plt
import japanize_matplotlib
import io
import time
from db import get_supabase_client

def generate_and_upload_reports():
    supabase = get_supabase_client()
    
    # 1. データの取得
    response = supabase.table('logs').select('*').order('date').execute()
    records = response.data

    if not records:
        return None, None

    # 直近7日分のデータに絞る
    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.tail(7)

    # ----- ① グラフ画像の作成 -----
    plt.figure(figsize=(10, 6))
    
    plt.plot(df.index, df['cond'], label='実際の調子', marker='o', color='darkorange', linewidth=2)
    plt.plot(df.index, df['pred'], label='予報Pt', marker='x', color='royalblue', linestyle='--')
    plt.bar(df.index, df['melan'], label='憂鬱さ', color='gray', alpha=0.3, width=0.5)

    plt.title('直近7日間のメンタルと予報の推移', fontsize=16)
    plt.ylim(0, 10)
    plt.yticks(range(11))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend(loc='upper left')
    
    # 日付ラベルを見やすくフォーマット (例: 8/7)
    df.index = df.index.strftime('%m/%d')
    plt.xticks(df.index)
    plt.tight_layout()

    # 画像データをメモリ上に保存
    graph_buf = io.BytesIO()
    plt.savefig(graph_buf, format='png', dpi=100)
    graph_buf.seek(0)
    plt.close()

    # ----- ② エクセル風の表画像の作成 -----
    # 表示用のデータフレームを整理
    table_df = df[['cond', 'melan', 'pred']].copy()
    table_df.columns = ['調子', '憂鬱さ', '予報Pt']
    
    # 表の描画設定
    fig, ax = plt.subplots(figsize=(6, 3)) 
    ax.axis('off')
    
    table = ax.table(cellText=table_df.values,
                     rowLabels=table_df.index,
                     colLabels=table_df.columns,
                     cellLoc='center',
                     loc='center')
    
    # 見た目の調整
    table.scale(1, 1.5)
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    
    table_buf = io.BytesIO()
    plt.savefig(table_buf, format='png', dpi=100, bbox_inches='tight')
    table_buf.seek(0)
    plt.close()

    # ----- ③ Supabase Storage へアップロード -----
    timestamp = int(time.time())
    graph_filename = f"graph_{timestamp}.png"
    table_filename = f"table_{timestamp}.png"

    # グラフのアップロード
    supabase.storage.from_("reports").upload(
        path=graph_filename,
        file=graph_buf.read(),
        file_options={"content-type": "image/png"}
    )
    # 表のアップロード
    supabase.storage.from_("reports").upload(
        path=table_filename,
        file=table_buf.read(),
        file_options={"content-type": "image/png"}
    )

    # 公開URLの取得
    graph_url = supabase.storage.from_("reports").get_public_url(graph_filename)
    table_url = supabase.storage.from_("reports").get_public_url(table_filename)

    return graph_url, table_url
