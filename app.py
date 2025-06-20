from flask import Flask, request
import os
import requests

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # Googleマップ検索URLを生成
            base_url = "https://www.google.com/maps/search/?api=1&query="
            search_url = base_url + requests.utils.quote(user_message)

            # LINEに返信
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            data = {
                "replyToken": reply_token,
                "messages": [{
                    "type": "text",
                    "text": f"こちらで検索できます！\n{search_url}"
                }]
            }
            requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=data)
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
