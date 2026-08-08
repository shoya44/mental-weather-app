import os
import google.generativeai as genai

def generate_weekly_advice(records):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not records:
        return "直近の記録データが不足しているため、振り返りを生成できませんでした。"

    genai.configure(api_key=api_key)
    
    # 【ここを修正】提供終了した 1.5 から最新の 2.5 モデルへ変更
    model = genai.GenerativeModel('gemini-2.5-flash')

    # AIに渡すデータのテキスト化
    data_summary = ""
    for r in records:
        date = r.get('date', '')
        cond = r.get('cond', '-')
        melan = r.get('melan', '-')
        memo = r.get('memo', 'なし')
        env = r.get('env', {})
        wx = env.get('fcst', {}).get('wx_jp', '-')
        data_summary += f"- {date}: 調子{cond}/9, 憂鬱さ{melan}/3, 天気:{wx}, メモ:「{memo}」\n"

    prompt = f"""
あなたはユーザーの優しく寄り添うメンタルヘルスのアドバイザーです。
以下はユーザーの直近数日間の記録（調子、憂鬱さ、天気、ひとことメモ）です。

【データ】
{data_summary}

【依頼】
このデータを踏まえて、ユーザーに対して温かく寄り添う「1週間の振り返りアドバイス」を200〜300文字程度で作成してください。
天気の変化や本人の調子・メモの言葉に優しく触れながら、労いの言葉と明日からのアドバイスを添えてください。絵文字も適度に使ってください。
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"申し訳ありません。AIアドバイスの生成中にエラーが発生しました。\n詳細: {e}"
