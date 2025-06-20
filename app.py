from flask import Flask, request
import os
import requests
import openai

app = Flask(__name__)

# 環境変数でLINEとOpenAIのAPIキーを管理
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# 参考にするサイト一覧。ここに辞書を追加するだけで拡張できます
REFERENCE_SITES = [
    {"name": "五島市観光協会公式サイト", "url": "https://goto.nagasaki-tabinet.com/", "type": "観光"},
    {"name": "fullygoto公式サイト", "url": "https://www.fullygoto.com/", "type": "観光"},
    {"name": "新上五島町観光物産協会公式サイト", "url": "https://official.shinkamigoto.net/", "type": "観光"},
    {"name": "小値賀町アイランドツーリズム協会公式サイト", "url": "https://ojikajima.jp/", "type": "観光"},
    {"name": "宇久町観光協会公式サイト", "url": "https://www.ukujima.com/", "type": "観光"},
    # 今後追加したい場合は、下のように1行追加するだけです
    # {"name": "新しいサイト名", "url": "https://newsite.com/", "type": "天気"},
]

# メッセージの内容から、Google Map案内 or AI要約を判定
def classify_message(text):
    # 場所系ワードが入っていたらGoogle Map、それ以外はWeb要約
    MAP_KEYWORDS = ["どこ", "場所", "行き方", "アクセス", "マップ", "地図"]
    if any(kw in text for kw in MAP_KEYWORDS):
        return "map"
    else:
        return "web"

# ChatGPTで観光サイトの要約案内文を生成
def generate_web_summary(user_message):
    sites_info = "\n".join([f"{site['name']}: {site['url']}" for site in REFERENCE_SITES])
    prompt = f"""下記の五島の観光サイトを参考に、「{user_message}」について旅行者向けに200文字程度で案内文を作成してください。回答には参考サイト名やURLも含めてください。
{sites_info}
"""
    openai.api_key = OPENAI_API_KEY
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "あなたは五島の観光案内AIです。"},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message['content']
except Exception as e:
    print("OpenAI APIエラー:", e)  # ここを追加
    raise

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            mode = classify_message(user_message)
            if mode == "map":
                # Googleマップ検索URLを生成
                base_url = "https://www.google.com/maps/search/?api=1&query="
                search_url = base_url + requests.utils.quote(user_message)
                reply_text = f"こちらで検索できます！\n{search_url}"
            else:
                # ChatGPTで観光サイトを参照した案内を作成
                try:
                    reply_text = generate_web_summary(user_message)
                except Exception as e:
                    reply_text = "AIによる案内文生成中にエラーが発生しました。時間を置いて再度お試しください。"

            # LINEに返信
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
            requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=data)
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
