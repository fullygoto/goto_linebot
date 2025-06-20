from flask import Flask, request
import os
import requests
from openai import OpenAI

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
print("LINE_CHANNEL_ACCESS_TOKEN:", LINE_CHANNEL_ACCESS_TOKEN, flush=True)
print("OPENAI_API_KEY:", OPENAI_API_KEY, flush=True)

REFERENCE_SITES = [
    {"name": "五島市観光協会公式サイト", "url": "https://goto.nagasaki-tabinet.com/", "type": "観光"},
    {"name": "fullygoto公式サイト", "url": "https://www.fullygoto.com/", "type": "観光"},
    {"name": "新上五島町観光物産協会公式サイト", "url": "https://official.shinkamigoto.net/", "type": "観光"},
    {"name": "小値賀町アイランドツーリズム協会公式サイト", "url": "https://ojikajima.jp/", "type": "観光"},
    {"name": "宇久町観光協会公式サイト", "url": "https://www.ukujima.com/", "type": "観光"},
]

def classify_message(text):
    return "web"  # デバッグ用（常にAI案内）

def generate_web_summary(user_message):
    print("AI生成開始: ", user_message, flush=True)
    sites_info = "\n".join([f"{site['name']}: {site['url']}" for site in REFERENCE_SITES])
    prompt = f"""下記の五島の観光サイトを参考に、「{user_message}」について旅行者向けに200文字程度で案内文を作成してください。回答には参考サイト名やURLも含めてください。
{sites_info}
"""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは五島の観光案内AIです。"},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content
        print("AI案内文:", answer, flush=True)
        return answer
    except Exception as e:
        print("OpenAI APIエラー:", e, flush=True)
        return "AIによる案内文生成中にエラーが発生しました。サーバーログをご確認ください。"

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])
    print("Webhook受信:", body, flush=True)
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            mode = classify_message(user_message)
            print("mode判定:", mode, flush=True)
            if mode == "map":
                base_url = "https://www.google.com/maps/search/?api=1&query="
                search_url = base_url + requests.utils.quote(user_message)
                reply_text = f"こちらで検索できます！\n{search_url}"
            else:
                reply_text = generate_web_summary(user_message)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            data = {
                "replyToken": reply_token,
                "messages": [{
                    "type": "text",
                    "text": reply_text
                }]
            }
            print("LINE送信データ:", data, flush=True)
            resp = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=data)
            print("LINE応答ステータス:", resp.status_code, flush=True)
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"サーバー起動: http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port)
