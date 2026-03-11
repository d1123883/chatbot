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

def rebuild_chat_from_history(history):
    """根據歷史紀錄重建 chat session"""
    global chat
    chat = client.chats.create(model=model_name)
    # 把截斷後的歷史逐輪重新發送給 Gemini，讓它恢復上下文
    for i in range(0, len(history), 2):
        if i + 1 < len(history):
            user_msg = history[i]["content"]
            # 重新發送訊息以重建上下文（忽略回應，因為我們已有歷史）
            chat.send_message(user_msg)

def respond(message, chat_history, file_obj):
    """Gradio 對話函式"""
    file_ref = None
    if file_obj:
        file_ref = upload_file_logic(file_obj.name)
        prompt = ["請分析這份檔案:", file_ref, message]
    else:
        prompt = message

    response = chat.send_message(prompt)
    
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response.text})
    
    return "", chat_history, None

def get_user_messages(chat_history):
    """取得所有使用者訊息作為下拉選單選項"""
    choices = []
    msg_index = 0
    for item in chat_history:
        if item["role"] == "user":
            msg_index += 1
            label = f"[{msg_index}] {item['content'][:50]}"
            if len(item['content']) > 50:
                label += "..."
            choices.append(label)
    return choices

def on_select_message(selection, chat_history):
    """當使用者選擇一則訊息時，將其內容填入編輯框"""
    if not selection:
        return ""
    # 從選項中取得訊息索引 (1-based)
    idx = int(selection.split("]")[0].replace("[", "")) - 1
    # 找到第 idx 個 user 訊息
    user_count = 0
    for item in chat_history:
        if item["role"] == "user":
            if user_count == idx:
                return item["content"]
            user_count += 1
    return ""

def edit_and_regenerate(selection, edited_message, chat_history, file_obj):
    """修改訊息並從該點重新產生回應"""
    if not selection or not edited_message:
        return edited_message, chat_history, None, gr.update(choices=[], value=None)
    
    # 從選項中取得訊息索引 (1-based)
    idx = int(selection.split("]")[0].replace("[", "")) - 1
    
    # 找到第 idx 個 user 訊息在 chat_history 中的實際位置
    user_count = 0
    cut_position = 0
    for i, item in enumerate(chat_history):
        if item["role"] == "user":
            if user_count == idx:
                cut_position = i
                break
            user_count += 1
    
    # 截斷歷史：保留該訊息之前的紀錄
    truncated_history = chat_history[:cut_position]
    
    # 重建 chat session（用截斷後的歷史重建上下文）
    if truncated_history:
        rebuild_chat_from_history(truncated_history)
    else:
        global chat
        chat = client.chats.create(model=model_name)
    
    # 發送修改後的訊息
    file_ref = None
    if file_obj:
        file_ref = upload_file_logic(file_obj.name)
        prompt = ["請分析這份檔案:", file_ref, edited_message]
    else:
        prompt = edited_message
    
    response = chat.send_message(prompt)
    
    truncated_history.append({"role": "user", "content": edited_message})
    truncated_history.append({"role": "assistant", "content": response.text})
    
    return "", truncated_history, None, gr.update(choices=[], value=None)

def refresh_edit_dropdown(chat_history):
    """更新下拉選單的選項"""
    choices = get_user_messages(chat_history)
    return gr.update(choices=choices, value=None)

# GUI 建立
with gr.Blocks() as demo:
    gr.Markdown("# 🤖 Gemini 2.5 互動助手")
    
    chatbot = gr.Chatbot(label="對話紀錄")
    
    msg = gr.Textbox(label="輸入問題", placeholder="在這裡輸入文字...")
    file_input = gr.File(label="上傳檔案 (圖片/PDF)")
    submit = gr.Button("發送")

    gr.Markdown("---")
    gr.Markdown("### ✏️ 修改先前的訊息")
    
    with gr.Row():
        refresh_btn = gr.Button("🔄 載入訊息列表", scale=1)
    
    edit_dropdown = gr.Dropdown(label="選擇要修改的訊息", choices=[], interactive=True)
    edit_textbox = gr.Textbox(label="修改訊息內容", placeholder="選擇訊息後在此編輯...", lines=3)
    edit_submit = gr.Button("📝 送出修改並重新產生回應")

    # 發送新訊息
    submit.click(respond, inputs=[msg, chatbot, file_input], outputs=[msg, chatbot, file_input])
    
    # 修改訊息功能
    refresh_btn.click(refresh_edit_dropdown, inputs=[chatbot], outputs=[edit_dropdown])
    edit_dropdown.change(on_select_message, inputs=[edit_dropdown, chatbot], outputs=[edit_textbox])
    edit_submit.click(
        edit_and_regenerate, 
        inputs=[edit_dropdown, edit_textbox, chatbot, file_input], 
        outputs=[edit_textbox, chatbot, file_input, edit_dropdown]
    )

if __name__ == "__main__":
    demo.launch()