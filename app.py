from flask import Flask, request
import os
import requests
from openai import OpenAI
import PyPDF2
import glob

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATA_DIR = "data"

# PDF/TXTデータの全文をロード
def load_all_texts(data_dir=DATA_DIR):
    texts = []
    # PDF
    for filepath in glob.glob(os.path.join(data_dir, "*.pdf")):
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text: texts.append(text)
    # TXT
    for filepath in glob.glob(os.path.join(data_dir, "*.txt")):
        with open(filepath, "r", encoding="utf-8") as f:
            texts.append(f.read())
    return texts

ALL_TEXTS = load_all_texts()

# 簡易キーワード検索（AND条件）
def search_best_paragraph(user_message, texts=ALL_TEXTS):
    user_message = user_message.strip()
    best = ""
    max_count = 0
    for text in texts:
        for para in text.split("\n"):
            count = sum([1 for w in user_message.split() if w in para])
            if count > max_count:
                max_count = count
                best = para
    return best.strip() if best else ""

# “行き方”系のワード判定
def is_googlemap_query(user_message):
    # 必要に応じてワード追加
    keywords = [
        "アクセス", "行き方", "場所", "マップ", "地図", "場所を教えて", "飲食店", "レストラン", "カフェ",
        "どうやって行く", "行く方法", "何分", "最寄り駅", "近くの", "ここまでの行き方", "どうやって行けば"
    ]
    msg = user_message.lower()
    return any(kw in msg for kw in keywords)

# AI回答（根拠テキストのみで、なければ「情報ありません」）
def generate_answer(user_message):
    related_text = search_best_paragraph(user_message)
    if not related_text or len(related_text) < 10:
        return None  # 根拠なし
    prompt = (
        f"あなたは五島の観光案内AIです。下記参考情報に根拠がある場合のみ正確に答えてください。"
        "情報がなければ『情報がありません』とだけ返してください。\n\n"
        f"【参考情報】\n{related_text}"
    )
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ]
        )
        answer = response.choices[0].message.content.strip()
        if "情報がありません" in answer or "分かりません" in answer or "お答えできません" in answer:
            return None
        return answer
    except Exception as e:
        print("OpenAI APIエラー:", e, flush=True)
        return None

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # ① アクセス・行き方・飲食店など特定質問にはGoogleマップ検索リンク
            if is_googlemap_query(user_message):
                base_url = "https://www.google.com/maps/search/?api=1&query="
                search_url = base_url + requests.utils.quote(user_message)
                reply_text = f"Googleマップで検索できます！\n{search_url}"
            else:
                # ② それ以外は根拠ある場合だけAI回答。なければ「情報がありません」
                reply_text = generate_answer(user_message)
                if not reply_text:
                    reply_text = "すみません、その件については現在の情報ではお答えできません。"

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
