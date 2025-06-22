from flask import Flask, request
import os
import glob
import requests
from openai import OpenAI
import PyPDF2
import chromadb
from chromadb.utils import embedding_functions
from bs4 import BeautifulSoup

# Selenium用
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATA_DIR = "data"

# Embedding function (OpenAI)
ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=OPENAI_API_KEY,
    model_name="text-embedding-3-small"
)

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="goto_kanko", embedding_function=ef)

# テキスト分割
def split_text_paragraphs(text, window=10, step=5):
    lines = text.split('\n')
    chunks = []
    for i in range(0, len(lines), step):
        chunk = "\n".join(lines[i:i+window])
        if len(chunk.strip()) >= 30:
            chunks.append(chunk)
    return chunks

# データ再投入
def load_docs_to_db():
    for filepath in glob.glob(os.path.join(DATA_DIR, "*.pdf")):
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text: continue
                chunks = split_text_paragraphs(text)
                for idx, chunk in enumerate(chunks):
                    docid = f"{os.path.basename(filepath)}-p{i}-c{idx}"
                    collection.add(
                        documents=[chunk],
                        metadatas=[{"file": os.path.basename(filepath), "page": i, "chunk": idx}],
                        ids=[docid]
                    )
    for filepath in glob.glob(os.path.join(DATA_DIR, "*.txt")):
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        chunks = split_text_paragraphs(text)
        for idx, chunk in enumerate(chunks):
            docid = f"{os.path.basename(filepath)}-c{idx}"
            collection.add(
                documents=[chunk],
                metadatas=[{"file": os.path.basename(filepath), "chunk": idx}],
                ids=[docid]
            )
    print("再投入後ドキュメント数:", collection.count())

# 最初だけ初期化
if collection.count() == 0:
    load_docs_to_db()

# ChromaDB検索
def search_paragraph(user_message):
    title_query = user_message.replace("について", "").replace("を教えて", "")
    res = collection.get(where_document={"$contains": title_query})
    if res and res['documents']:
        return res['documents'][0]
    search_res = collection.query(query_texts=[user_message], n_results=1)
    if search_res and search_res['documents'][0]:
        return search_res['documents'][0][0]
    return ""

# SeleniumによるHTML取得
def get_html_with_selenium(url):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    driver.get(url)
    html = driver.page_source
    driver.quit()
    return html

# 九州商船 長崎～五島航路運行状況スクレイピング（requests→なければSeleniumで再取得）
def get_kyusho_ferry_status():
    url = "https://kyusho.co.jp/status"
    try:
        # 1. まずrequestsでアクセス
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.content, "html.parser")
        nagasaki_goto = soup.find("div", class_="js-swich-target", attrs={"data-swich": "nagasaki_goto"})

        # 2. requestsで見つからなければSeleniumで再取得
        if not nagasaki_goto:
            html = get_html_with_selenium(url)
            soup = BeautifulSoup(html, "html.parser")
            nagasaki_goto = soup.find("div", class_="js-swich-target", attrs={"data-swich": "nagasaki_goto"})
        
        if not nagasaki_goto:
            return "運航状況の取得エリアが見つかりませんでした。"

        result = ""
        sections = nagasaki_goto.find_all("section", recursive=False)
        for section in sections:
            title = section.find("h3")
            if title:
                result += f"【{title.text.strip()}】\n"
            port_sections = section.find_all("section", recursive=False)
            for port in port_sections:
                port_name = port.find("h4")
                if not port_name:
                    continue
                port_name = port_name.text.strip()
                table = port.find("table")
                if not table:
                    continue
                rows = table.find_all("tr")
                for row in rows:
                    time_th = row.find("th")
                    status_td = row.find("td", class_="unkou")
                    if not time_th or not status_td:
                        continue
                    time_str = time_th.text.strip()
                    img = status_td.find("img")
                    status = img["alt"] if img and "alt" in img.attrs else ""
                    result += f"{port_name}：{time_str} {status}\n"
        if not result:
            return "長崎〜五島航路の運航状況が見つかりませんでした。"
        return result.strip()
    except Exception as e:
        print("スクレイピングエラー:", e)
        return "運行情報の取得中にエラーが発生しました。"

# 回答生成
def generate_answer(user_message):
    # 九州商船運行状況キーワードなら
    if ("九州商船" in user_message) or ("五島航路" in user_message) or \
       ("長崎" in user_message and "運航" in user_message):
        return get_kyusho_ferry_status()
    related_text = search_paragraph(user_message)
    if not related_text or len(related_text) < 10:
        return "すみません、その件については現在の情報ではお答えできません。"
    prompt = (
        "あなたは五島の観光公式AIです。以下の参考情報だけを根拠に、事実のみ正確に答えてください。"
        "根拠が不十分な場合は「情報がありません」と返してください。\n\n"
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
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI APIエラー:", e, flush=True)
        return "AIによる案内文生成中にエラーが発生しました。"

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    events = body.get("events", [])
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]
            reply_text = generate_answer(user_message)
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

# DB再投入API
@app.route("/reload", methods=["POST"])
def reload_db():
    try:
        collection.delete()
        load_docs_to_db()
        return "DBリロード完了"
    except Exception as e:
        print("リロードエラー:", e)
        return f"リロード失敗: {e}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
