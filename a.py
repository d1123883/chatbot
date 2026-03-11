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

# 1. 初始化
script_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=script_dir / '.env')
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
model_name = "gemini-2.5-flash"

# --- 人格設定庫 (你可以在這裡新增你的 Prompt) ---
PERSONAS = {
    "專業助理": "你是一位專業、有效率且語氣客觀的 AI 助理。",
    "吐槽大師": "你是一個喜歡用幽默、毒舌、吐槽語氣說話的朋友。",
    "蘇格拉底老師": "你是一位哲學家，不直接給答案，而是透過引導式的反問來啟發使用者思考。",
    "超級程式員": "你是一位頂尖的資深程式工程師，專注於提供乾淨、高效且有註解的程式碼。"
}

# 全域變數來儲存當前的 chat 物件
current_chat = None
current_persona = ""

def get_chat_object(persona_name):
    """根據人格名稱取得對應的 chat 物件"""
    system_prompt = PERSONAS.get(persona_name, "你是一個 AI 助理。")
    # 設定系統指令 (System Instruction)
    config = types.GenerateContentConfig(system_instruction=system_prompt)
    return client.chats.create(model=model_name, config=config)

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

def respond(message, chat_history, file_obj, persona_name):
    """核心對話函式"""
    global current_chat, current_persona
    
    # 如果人格改變，重置 chat 物件
    if current_persona != persona_name:
        current_chat = get_chat_object(persona_name)
        current_persona = persona_name
        chat_history = [] # 重置對話紀錄

    # 處理檔案
    file_ref = None
    if file_obj:
        file_ref = upload_file_logic(file_obj.name)
        prompt = ["請分析這份檔案:", file_ref, message]
    else:
        prompt = message

    response = current_chat.send_message(prompt)
    
    # 更新紀錄 (字典格式)
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response.text})
    
    return "", chat_history, None 

# 3. 建立 GUI
with gr.Blocks() as demo:
    gr.Markdown("# 🤖 Gemini 2.5 多人格助手")
    
    persona_dropdown = gr.Dropdown(
        choices=list(PERSONAS.keys()), 
        label="選擇人格", 
        value="專業助理"
    )
    
    chatbot = gr.Chatbot(label="對話紀錄")
    msg = gr.Textbox(label="輸入問題", placeholder="在這裡輸入文字...")
    file_input = gr.File(label="上傳檔案 (圖片/PDF)")
    submit = gr.Button("發送")

    # 按鈕互動
    submit.click(
        respond, 
        inputs=[msg, chatbot, file_input, persona_dropdown], 
        outputs=[msg, chatbot, file_input]
    )

if __name__ == "__main__":
    demo.launch()