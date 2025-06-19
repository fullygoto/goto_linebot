from flask import Flask, request
import openai
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])

    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # 【ここを最新版の記法に】
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "あなたは五島観光のAI案内人です。"},
                    {"role": "user", "content": user_message}
                ]
            )
            reply_text = response.choices[0].message.content

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            reply_data = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": reply_text}]
            }

            requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=reply_data)

    return "OK"


if __name__ == "__main__":
    app.run()
