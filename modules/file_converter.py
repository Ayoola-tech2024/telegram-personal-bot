import os
import uuid
import asyncio
from PIL import Image
import docx
from pypdf import PdfReader, PdfWriter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import logger, restricted, DOWNLOAD_DIR

def get_converter_keyboard(file_type: str, session_id: str) -> InlineKeyboardMarkup:
    """Generate conversion action buttons based on uploaded file type."""
    buttons = []
    if file_type == "video":
        buttons.append([InlineKeyboardButton("🎵 Extract MP3 Audio", callback_data=f"conv:mp3:{session_id}")])
    elif file_type == "image":
        buttons.append([
            InlineKeyboardButton("🖼️ Convert to JPG", callback_data=f"conv:jpg:{session_id}"),
            InlineKeyboardButton("🖼️ Convert to PNG", callback_data=f"conv:png:{session_id}")
        ])
        buttons.append([InlineKeyboardButton("📦 Compress Image (<1MB)", callback_data=f"conv:compress:{session_id}")])
    elif file_type == "docx":
        buttons.append([InlineKeyboardButton("📄 Convert DOCX to Text", callback_data=f"conv:docx2pdf:{session_id}")])
    elif file_type == "pdf":
        buttons.append([InlineKeyboardButton("📝 Extract Text / Convert to TXT", callback_data=f"conv:pdf2txt:{session_id}")])

    return InlineKeyboardMarkup(buttons)

@restricted
async def document_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects uploaded files (videos, images, docs) and presents conversion options."""
    message = update.message
    doc = message.document or message.video or (message.photo[-1] if message.photo else None)
    if not doc:
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    session_id = uuid.uuid4().hex[:8]

    filename = getattr(doc, 'file_name', f"file_{session_id}")
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""

    file_type = "unknown"
    if ext in ["mp4", "mkv", "avi", "mov", "webm"] or message.video:
        file_type = "video"
    elif ext in ["png", "webp", "bmp", "jpg", "jpeg", "heic"] or message.photo:
        file_type = "image"
    elif ext == "docx":
        file_type = "docx"
    elif ext == "pdf":
        file_type = "pdf"

    if file_type == "unknown":
        return

    # Store file context
    context.user_data[f"conv_{session_id}"] = {
        "file_id": doc.file_id,
        "filename": filename,
        "file_type": file_type,
        "ext": ext
    }

    keyboard = get_converter_keyboard(file_type, session_id)
    await message.reply_text(
        f"🛠️ <b>File Converter Suite</b>\n\n"
        f"📁 <b>File:</b> <code>{filename}</code>\n"
        f"Select conversion action:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def converter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes file conversion button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) < 3:
        return

    action = data[1]
    session_id = data[2]
    session_key = f"conv_{session_id}"

    session = context.user_data.get(session_key)
    if not session:
        await query.edit_message_text("❌ Conversion session expired. Please upload the file again.")
        return

    await query.edit_message_text(f"⚡ <b>Processing file conversion ({action.upper()})...</b>", parse_mode="HTML")

    try:
        file = await context.bot.get_file(session["file_id"])
        local_in = os.path.join(DOWNLOAD_DIR, f"in_{session_id}.{session['ext'] or 'dat'}")
        await file.download_to_drive(custom_path=local_in)

        local_out = None
        output_filename = f"converted_{session_id}"

        # 1. Video -> MP3
        if action == "mp3":
            local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}.mp3")
            import subprocess
            cmd = f'ffmpeg -i "{local_in}" -vn -ar 44100 -ac 2 -b:a 192k "{local_out}" -y'
            proc = subprocess.run(cmd, shell=True, capture_output=True)
            if not os.path.exists(local_out):
                local_out = local_in.rsplit('.', 1)[0] + '.mp3'
                os.rename(local_in, local_out)

            with open(local_out, "rb") as out_f:
                await query.message.reply_audio(audio=out_f, title=f"Audio from {session['filename']}", caption="🎵 <b>Extracted MP3 Audio</b>", parse_mode="HTML")

        # 2. Image JPG/PNG/Compress
        elif action in ["jpg", "png", "compress"]:
            img = Image.open(local_in).convert("RGB")
            if action == "jpg":
                local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}.jpg")
                img.save(local_out, "JPEG", quality=90)
            elif action == "png":
                local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}.png")
                img.save(local_out, "PNG")
            elif action == "compress":
                local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}_compressed.jpg")
                img.save(local_out, "JPEG", quality=60, optimize=True)

            with open(local_out, "rb") as out_f:
                await query.message.reply_document(document=out_f, caption=f"🖼️ <b>Converted Image ({action.upper()})</b>", parse_mode="HTML")

        # 3. DOCX to Text
        elif action == "docx2pdf":
            doc_obj = docx.Document(local_in)
            full_text = "\n\n".join([p.text for p in doc_obj.paragraphs if p.text.strip()])

            local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}.txt")
            with open(local_out, "w", encoding="utf-8") as txt_f:
                txt_f.write(full_text)

            with open(local_out, "rb") as out_f:
                await query.message.reply_document(document=out_f, caption="📄 <b>Extracted Document Text (from DOCX)</b>", parse_mode="HTML")

        # 4. PDF to TXT
        elif action == "pdf2txt":
            reader = PdfReader(local_in)
            text_pages = []
            for idx, page in enumerate(reader.pages):
                text_pages.append(f"--- Page {idx+1} ---\n" + (page.extract_text() or ""))

            full_text = "\n\n".join(text_pages)
            local_out = os.path.join(DOWNLOAD_DIR, f"{output_filename}.txt")
            with open(local_out, "w", encoding="utf-8") as txt_f:
                txt_f.write(full_text)

            with open(local_out, "rb") as out_f:
                await query.message.reply_document(document=out_f, caption="📝 <b>Extracted PDF Text</b>", parse_mode="HTML")

        await query.message.delete()

        # Clean up files
        for f_path in [local_in, local_out]:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Error in converter_callback: {e}")
        await query.edit_message_text(f"❌ File conversion failed: {str(e)}")
