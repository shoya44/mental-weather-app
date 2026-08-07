import os
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, PushMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from weather import get_weather_and_calc_adj
from db import save_and_predict

load_dotenv()
app = Flask(__name__)

configuration = Configuration(access_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

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

LINE_USER_ID = os.environ.get('LINE_USER_ID')
CRON_SECRET = os.environ.get('CRON_SECRET')

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
            items = [QuickReplyItem(action=MessageAction(label=str(i), text=f"調子:{i}")) for i in range(10)]
            msg = TextMessage(
                text="【夕刊の時間です】\n今日の調子は？(0~9)",
                quick_reply=QuickReply(items=items)
            )
            line_bot_api.push_message(
                PushMessageRequest(
                    to=LINE_USER_ID,
                    messages=[msg]
                )
            )
        return "Notification sent!", 200
    except Exception as e:
        print(f"Push Notification Error: {e}")
        return "Failed to send notification", 500

@app.route("/", methods=['GET'])
def hello():
    return "Vercelサーバーは正常に動いています！"

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
            # ① 「夕刊」で調子選択
            if user_text == "夕刊":
                items = [QuickReplyItem(action=MessageAction(label=str(i), text=f"調子:{i}")) for i in range(10)]
                msg = TextMessage(
                    text="今日の調子は？(0~9)",
                    quick_reply=QuickReply(items=items)
                )
                
            # ② 憂鬱さ選択
            elif user_text.startswith("調子:"):
                cond_val = user_text.split(":")[1]
                items = [QuickReplyItem(action=MessageAction(label=str(i), text=f"記録:{cond_val}:{i}")) for i in range(4)]
                msg = TextMessage(
                    text=f"調子: {cond_val}ですね。明日の憂鬱さは？(0:なし~3:かなり)",
                    quick_reply=QuickReply(items=items)
                )
                
            # ③ 記録完了と予報表示
            elif user_text.startswith("記録:"):
                _, cond_val, melan_val = user_text.split(":")
                
                # 天気取得・計算・DB保存
                env_data = get_weather_and_calc_adj(melan_val)
                pred_val, match_count = save_and_predict(cond_val, melan_val, env_data)
                
                mental_wx_label = get_mental_weather_label(pred_val)
                fcst = env_data["fcst"]
                diff = env_data["diff"]
                fmt_pt = env_data["fmt_pt"]
                
                diff_t_str = f"+{diff['t_max']}" if diff['t_max'] > 0 else str(diff['t_max'])
                diff_p_str = f"+{diff['p_min']}" if diff['p_min'] > 0 else str(diff['p_min'])

                reply_text = (
                    f"調子: {cond_val}, 憂鬱さ: {melan_val} で記録しました！\n\n"
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
                msg = TextMessage(text="「夕刊」と送ると記録が始まります。")

        except Exception as e:
            print(f"Error handling message: {e}")
            msg = TextMessage(text="申し訳ありません。気象データの取得または計算中にエラーが発生しました。時間をおいて再度お試しください。")
            
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[msg]
            )
        )

if __name__ == "__main__":
    app.run(port=5000, debug=True)
