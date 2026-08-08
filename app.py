import os
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, PushMessageRequest,
    TextMessage, ImageMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from weather import get_weather_and_calc_adj
from db import save_and_predict, get_recent_logs
from report import generate_and_upload_reports
from ai import generate_weekly_advice

load_dotenv()
app = Flask(__name__)

configuration = Configuration(access_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

LINE_USER_ID = os.environ.get('LINE_USER_ID')
CRON_SECRET = os.environ.get('CRON_SECRET')

def get_mental_weather_label(pred_val):
    if pred_val >= 8:
        return f"快晴☀️ ({pred_val}Pt)"
    elif pred_val >= 6:
        return f"晴れ🌤️ ({pred_val}Pt)"
    elif pred_val >= 4:
        return f"くもり☁️ ({pred_val}Pt)"
    elif pred_val >= 2:
        return f"小雨☔ ({pred_val}Pt)"
    else:
        return f"大雨⛈️ ({pred_val}Pt)"

GUIDE_MESSAGE = (
    "【夕刊の時間です 📝】\n"
    "今日の記録をカンマ区切りで送ってね！\n\n"
    "入力順：調子,憂鬱さ,ひとことメモ\n"
    "入力例） 5,0,仕事が疲れた\n\n"
    "※調子: 0~9, 憂鬱さ: 0~3\n"
    "※メモは省略可能です（例: 5,0）"
)

@app.route("/", methods=['GET'])
def hello():
    return "Vercelサーバーは正常に動いています！"

@app.route("/notify", methods=['GET', 'POST'])
def notify():
    secret = request.args.get('secret')
    if secret != CRON_SECRET:
        return "Unauthorized", 401
    
    if not LINE_USER_ID:
        return "LINE_USER_ID is not set", 500

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=LINE_USER_ID,
                    messages=[TextMessage(text=GUIDE_MESSAGE)]
                )
            )
        return "Notification sent!", 200
    except Exception as e:
        print(f"Push Notification Error: {e}")
        return "Failed to send notification", 500

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        user_text = event.message.text.strip()
        
        try:
            # ① 「夕刊」またはガイド要求
            if user_text == "夕刊":
                msg = TextMessage(text=GUIDE_MESSAGE)
                
            # ② 「レポート」出力
            elif user_text == "レポート":
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="レポートを作成中です...少しお待ちください⏳")]
                    )
                )
                graph_url, table_url = generate_and_upload_reports()
                
                if graph_url and table_url:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=event.source.user_id,
                            messages=[
                                ImageMessage(original_content_url=graph_url, preview_image_url=graph_url),
                                ImageMessage(original_content_url=table_url, preview_image_url=table_url)
                            ]
                        )
                    )
                else:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=event.source.user_id,
                            messages=[TextMessage(text="データがありません。何度か記録をつけてからお試しください！")]
                        )
                    )
                return 'OK'

            # ③ 「振り返り」AIアドバイス機能
            elif user_text == "振り返り":
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="今週の記録を分析して振り返りを作成中です...🤖💭")]
                    )
                )
                records = get_recent_logs(7)
                advice_text = generate_weekly_advice(records)
                
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=event.source.user_id,
                        messages=[TextMessage(text=f"【今週のAI振り返りアドバイス 🌿】\n\n{advice_text}")]
                    )
                )
                return 'OK'

            # ④ カンマ区切りの記録入力パース (例: "5,0,仕事が疲れた" または "5,0")
            elif "," in user_text or "，" in user_text:
                # 全角カンマも半角に統一して分割
                parts = user_text.replace("，", ",").split(",", 2)
                
                if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    cond_val = parts[0].strip()
                    melan_val = parts[1].strip()
                    memo_text = parts[2].strip() if len(parts) >= 3 else ""
                    
                    env_data = get_weather_and_calc_adj(melan_val)
                    pred_val, match_count = save_and_predict(cond_val, melan_val, memo_text, env_data)
                    
                    mental_wx_label = get_mental_weather_label(pred_val)
                    fcst = env_data["fcst"]
                    diff = env_data["diff"]
                    fmt_pt = env_data["fmt_pt"]
                    
                    diff_t_str = f"+{diff['t_max']}" if diff['t_max'] > 0 else str(diff['t_max'])
                    diff_p_str = f"+{diff['p_min']}" if diff['p_min'] > 0 else str(diff['p_min'])

                    memo_disp = f"\nメモ: 「{memo_text}」" if memo_text else ""

                    reply_text = (
                        f"調子: {cond_val}, 憂鬱さ: {melan_val}{memo_disp} で記録しました！\n\n"
                        f"【明日のメンタル予報(0~9)】\n"
                        f"{mental_wx_label}\n\n"
                        f"【明日の天気予報】\n"
                        f"・天気: {fcst['wx_jp']}({fmt_pt['wx']})\n"
                        f"・最高気温: {fcst['t_max']}℃ (前日比 {diff_t_str}℃: {fmt_pt['temp']})\n"
                        f"・湿度: {fcst['h_max']}%({fmt_pt['humid']})\n"
                        f"・最低気圧: {fcst['p_min']}hPa (前日比 {diff_p_str}hPa: {fmt_pt['pres']})\n\n"
                        f"※過去の類似データ{match_count}件に基づき、算出しました。\n"
                        f"明日も無理せず行きましょう！"
                    )
                    msg = TextMessage(text=reply_text)
                else:
                    msg = TextMessage(text="入力形式が正しくありません。\n例） 5,0,仕事が疲れた のように送ってください！")

            else:
                msg = TextMessage(text="「5,0,日記」のようにカンマ区切りで入力するか、メニューから選んでね！")

        except Exception as e:
            print(f"Error handling message: {e}")
            msg = TextMessage(text=f"処理中にエラーが発生しました。\n詳細: {e}")
            line_bot_api.push_message(
                PushMessageRequest(
                    to=event.source.user_id,
                    messages=[msg]
                )
            )
            return 'OK'
            
        if user_text not in ["レポート", "振り返り"]:
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[msg]
                )
            )

if __name__ == "__main__":
    app.run(port=5000, debug=True)
