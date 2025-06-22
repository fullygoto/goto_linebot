from flask import Flask, request
import os
import requests
from openai import OpenAI
import PyPDF2
import chromadb
from chromadb.utils import embedding_functions
import glob

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATA_DIR = "data"

# --- [1] Embedding関数の用意（OpenAI埋め込みAPI利用）
ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=OPENAI_API_KEY,
    model_name="text-embedding-3-small"
)

# --- [2] ChromaDBコレクション初期化
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="goto_kanko", embedding_function=ef)

# --- [3] テキストを一定行ごとに分割

def split_text_paragraphs(text, window=10, step=5):
    lines = text.split('\n')
    chunks = []
    for i in range(0, len(lines), step):
        chunk = "\n".join(lines[i:i+window])
        if len(chunk.strip()) >= 30:
            chunks.append(chunk)
    return chunks

# --- [4] data/フォルダ全PDF・TXTを分割→コレクションに投入

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

if collection.count() == 0:
    load_docs_to_db()

# --- [5] タイトル一致優先＋ベクトル類似検索

def search_paragraph(user_message):
    title_query = user_message.replace("について", "").replace("を教えて", "")
    res = collection.get(where_document={"$contains": title_query})
    if res and res['documents']:
        return res['documents'][0]
    search_res = collection.query(query_texts=[user_message], n_results=1)
    if search_res and search_res['documents'][0]:
        return search_res['documents'][0][0]
    return ""

def generate_answer(user_message):
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
