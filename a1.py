import os
import time
import mimetypes
import shutil
import tempfile
import gradio as gr
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 初始化
script_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=script_dir / '.env')
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
model_name = "gemini-2.5-flash"
chat = client.chats.create(model=model_name)

def upload_file_logic(file_path):
    temp_dir = Path(tempfile.gettempdir())
    safe_path = temp_dir / f"temp_upload{Path(file_path).suffix}"
    shutil.copy2(file_path, safe_path)
    
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'
        
    file_ref = client.files.upload(
        file=safe_path, 
        config=types.UploadFileConfig(mime_type=mime_type)
    )
    
    while file_ref.state.name == "PROCESSING":
        time.sleep(1)
        file_ref = client.files.get(name=file_ref.name)
    return file_ref

def respond(message, chat_history, file_obj):
    """Gradio 對話函式 (修正版)"""
    file_ref = None
    if file_obj:
        file_ref = upload_file_logic(file_obj.name)
        prompt = ["請分析這份檔案:", file_ref, message]
    else:
        prompt = message

    response = chat.send_message(prompt)
    
    # 【關鍵修正】：嚴格遵守字典格式
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response.text})
    
    return "", chat_history, None 

# GUI 建立
with gr.Blocks() as demo:
    gr.Markdown("# 🤖 Gemini 2.5 互動助手")
    
    # 這裡我們不寫 type="messages"，讓 Gradio 自動根據我們傳入的字典格式運作
    chatbot = gr.Chatbot(label="對話紀錄")
    
    msg = gr.Textbox(label="輸入問題", placeholder="在這裡輸入文字...")
    file_input = gr.File(label="上傳檔案 (圖片/PDF)")
    submit = gr.Button("發送")

    submit.click(respond, inputs=[msg, chatbot, file_input], outputs=[msg, chatbot, file_input])

if __name__ == "__main__":
    demo.launch()