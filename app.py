import os
from flask import Flask, request, abort
from dotenv import load_dotenv
from weather import get_weather_and_calc_adj
from db import save_and_predict

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, 
    TextMessage, QuickReply, QuickReplyItem, MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

load_dotenv()
app = Flask(__name__) # ←この行のすぐ下に追加する

@app.route("/", methods=['GET'])
def hello():
    return "Vercelサーバーは正常に動いています！"

configuration = Configuration(access_token=os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
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
        user_text = event.message.text
        
        # ①「夕刊」と送られたら、調子(0〜9)のボタンを出す
        if user_text == "夕刊":
            items = [QuickReplyItem(action=MessageAction(label=str(i), text=f"調子:{i}")) for i in range(10)]
            msg = TextMessage(
                text="今日の調子は？(0〜9)",
                quick_reply=QuickReply(items=items)
            )
            
        # ② 調子のボタンが押されたら... (書き換え)
        elif user_text.startswith("調子:"):
            cond_val = user_text.split(":")[1]
            # textの中に「記録:今日の調子:明日の憂鬱」という形で次の値を埋め込む
            items = [QuickReplyItem(action=MessageAction(label=str(i), text=f"記録:{cond_val}:{i}")) for i in range(4)]
            msg = TextMessage(
                text=f"調子 {cond_val} ですね。明日の憂鬱さは？\n(0:ない 〜 3:かなり)",
                quick_reply=QuickReply(items=items)
            )
            
        # ③ 憂鬱さのボタンが押されたら... (書き換え)
        elif user_text.startswith("記録:"):
            # 文字列を分割して、調子と憂鬱さを両方取り出す
            _, cond_val, melan_val = user_text.split(":")
            
            # APIから天気取得＆補正Ptを計算
            env_data = get_weather_and_calc_adj(melan_val)
            
            # データベース保存と予報Ptの算出！
            pred_val, match_count = save_and_predict(cond_val, melan_val, env_data)
            
            # LINEへ返すメッセージ
            logic_str = "過去の類似日の平均値" if match_count > 0 else "加減算の補正値"
            
            reply_text = (
                f"記録をSupabaseに保存しました！\n\n"
                f"【明日のメンタル予報】\n"
                f"予報Pt: {pred_val} \n\n"
                f"※過去の類似データ {match_count} 件に基づき、{logic_str}から算出しました。\n"
                f"明日も無理せずいきましょう！"
            )
            
            msg = TextMessage(text=reply_text)
            
        # ④ それ以外の言葉が送られたとき
        else:
            msg = TextMessage(text="「夕刊」と送ると記録が始まります。")
            
        # LINEにメッセージを返信
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[msg]
            )
        )

if __name__ == "__main__":
    app.run(port=5000, debug=True)