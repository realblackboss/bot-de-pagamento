import logging
import sqlite3
import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= CONFIGURAÇÕES ====================
BOT_TOKEN = "7651348112:AAFJh3lBDfUprrNxfaEsoqg7ag-T_1wE0ss"
ADMIN_IDS = [1005515503, 1609656649, 5451123398, 222222222, 333333333]

# ================= LOGGING ===================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= BANCO DE DADOS ==================
conn = sqlite3.connect("reallblackboss.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER,
    username TEXT,
    phone_number TEXT,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER,
    username TEXT,
    phone_number TEXT,
    name TEXT,
    amount REAL,
    status TEXT,
    proof_file_id TEXT
)
""")
conn.commit()

# ================= UTILITÁRIOS =====================
def get_user_info(update: Update):
    user = update.effective_user
    return user.id, user.username or "None", "None", user.full_name or "None"

def escape_markdown(text: str) -> str:
    """Escapa caracteres especiais do MarkdownV2"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# ================= HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Envia a imagem de boas-vindas primeiro
    try:
        image_path = os.path.join(os.getcwd(), "imagem de ingrenagem bot usuarios", "imagem usuario.png")
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(photo=photo)
        else:
            logger.warning("Imagem de usuário não encontrada")
    except Exception as e:
        logger.error(f"Erro ao enviar imagem de boas-vindas: {str(e)}")

    # Registra o usuário e envia mensagem de boas-vindas
    telegram_id, username, phone_number, name = get_user_info(update)
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (telegram_id, username, phone_number, name) VALUES (?, ?, ?, ?)",
            (telegram_id, username, phone_number, name)
        )
        conn.commit()

    message = (
        "🛠️ *Bem\\-vindo ao Bot D7Pagamentos\\!*\n\n"
        "Para adicionar saldo, use o comando:\n"
        "`/pay [valor]`\n\n"
        "Exemplo: `/pay 50`\n\n"
        "⚠️ *ATENÇÃO:*\n"
        "\\- Link válido por 10 minutos\n"
        "\\- Após o pagamento, envie o comprovante\n"
        "\\- Valores incorretos serão recusados"
    )
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id, username, phone_number, name = get_user_info(update)
    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Uso correto: /pay [valor]")
        return

    try:
        amount = float(context.args[0])
        cursor.execute(
            "INSERT INTO payments (telegram_id, username, phone_number, name, amount, status) VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, username, phone_number, name, amount, "pendente")
        )
        conn.commit()

        payment_link = "https://portal.p27pay.com.br/pay/725fe172"
        message = (
            f"💵 *PAGAMENTO DE R$ {amount:.2f}*\n\n"
            "👉 [CLIQUE AQUI PARA PAGAR](" + payment_link + ")\n\n"
            "⚠️ *ATENÇÃO:*\n"
            "- Link válido por 10 minutos\n"
            "- Após o pagamento, envie o comprovante\n"
            "- Valores incorretos serão recusados"
        )
        keyboard = [[InlineKeyboardButton("📤 Enviar Comprovante", callback_data="enviar_comprovante")]]
        await update.message.reply_text(
            message, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except ValueError:
        await update.message.reply_text("⚠️ Valor inválido! Use apenas números. Exemplo: /pay 100")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "enviar_comprovante":
        await query.message.reply_text("📎 Por favor, envie uma foto do comprovante de pagamento.")
    
    elif query.data.startswith("autorizar_"):
        payment_id = int(query.data[len("autorizar_"):])
        cursor.execute("UPDATE payments SET status = 'autorizado' WHERE id = ?", (payment_id,))
        conn.commit()
    
        cursor.execute("SELECT telegram_id FROM payments WHERE id = ?", (payment_id,))
        user_id = cursor.fetchone()[0]

        # ✅ Envio da mensagem com HTML parse_mode
        await context.bot.send_message(
            chat_id=user_id,
            text="<b>✅ Pagamento aprovado com sucesso!</b>",
            parse_mode=ParseMode.HTML
        )
    
        await query.message.delete()

    
    elif query.data.startswith("nao_autorizar_"):
        payment_id = int(query.data[len("nao_autorizar_"):])
        cursor.execute("UPDATE payments SET status = 'nao_autorizado' WHERE id = ?", (payment_id,))
        conn.commit()
        cursor.execute("SELECT telegram_id FROM payments WHERE id = ?", (payment_id,))
        user_id = cursor.fetchone()[0]
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Pagamento recusado. Por favor, gere um novo link com /start."
        )
        await query.message.delete()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id, username, phone_number, name = get_user_info(update)
    photo = update.message.photo[-1].file_id
    cursor.execute(
        "UPDATE payments SET proof_file_id = ? WHERE telegram_id = ? AND status = 'pendente'",
        (photo, telegram_id)
    )
    conn.commit()
    await update.message.reply_text("📨 Comprovante recebido! Aguarde a confirmação.")

async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return
    
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM payments")
    conn.commit()
    await update.message.reply_text("♻️ Todos os registros foram resetados.")

async def registros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    # 🔒 Define o teclado ANTES de qualquer possível uso
    keyboard = [
        [InlineKeyboardButton("👥 Registros de Usuários", callback_data="reg_cliques")],
        [InlineKeyboardButton("💳 Pagamentos Pendentes", callback_data="reg_pagamentos")],
        [InlineKeyboardButton("✅ Pagamentos Aprovados", callback_data="pag_autorizados")],
        [InlineKeyboardButton("❌ Pagamentos Recusados", callback_data="pag_nao_autorizados")],
        [InlineKeyboardButton("💰 Saldo Total", callback_data="saldo_ativo")],
    ]

    username = update.effective_user.username or update.effective_user.full_name
    welcome_msg = (
        f"👋 Olá, @{escape_markdown(username)}!\n\n"
        "🧾 *Bem\\-vindo ao painel administrativo do D7Pagamentos*"
    )
    await update.message.reply_text(
        welcome_msg,
        parse_mode=ParseMode.HTML
    )

    # 📎 Tenta enviar um arquivo da pasta de configurações
    config_dir = os.path.join(os.getcwd(), "imagem de ingrenagem bot D7PAGAMENTOSP27PAY")
    
    try:
        if os.path.exists(config_dir):
            files = [f for f in os.listdir(config_dir) if os.path.isfile(os.path.join(config_dir, f))]
            
            if files:
                file_path = os.path.join(config_dir, files[0])
                
                if files[0].lower().endswith(('.png', '.jpg', '.jpeg')):
                    with open(file_path, 'rb') as file:
                        await update.message.reply_photo(
                            photo=file,
                            caption="⚙️ Configurações do sistema"
                        )
                else:
                    with open(file_path, 'rb') as file:
                        await update.message.reply_document(
                            document=file,
                            caption="📁 Arquivo de configuração"
                        )
            else:
                await update.message.reply_text("ℹ️ Nenhum arquivo encontrado na pasta de configurações.")
        else:
            await update.message.reply_text("⚠️ Pasta de configurações não encontrada.")
            
    except Exception as e:
        logger.error(f"Erro ao enviar arquivo: {str(e)}")
        await update.message.reply_text("⚠️ Ocorreu um erro ao acessar as configurações.")

    # 🔒 Define o teclado ANTES de qualquer possível uso
    keyboard = [
       [InlineKeyboardButton("👥 Registros de Usuários", callback_data="reg_cliques")],
       [InlineKeyboardButton("💳 Pagamentos Pendentes", callback_data="reg_pagamentos")],
       [InlineKeyboardButton("✅ Pagamentos Aprovados", callback_data="pag_autorizados")],
       [InlineKeyboardButton("❌ Pagamentos Recusados", callback_data="pag_nao_autorizados")],
       [InlineKeyboardButton("💰 Saldo Total", callback_data="saldo_ativo")],
    ]

    # 🧭 Envia o menu final com o teclado
    await update.message.reply_text(
        "📊 *Menu de Navegação:*\nSelecione uma opção:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def registros_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("⛔ Acesso restrito.")
        return

    if query.data == "reg_cliques":
        cursor.execute("SELECT username, telegram_id, phone_number, name FROM users")
        users = cursor.fetchall()
        
        response = "📋 *REGISTROS DE USUÁRIOS*\n\n"
        for user in users:
            username = f"@{user[0]}" if user[0] and user[0] != "None" else "None"
            user_id = user[1] if user[1] else "None"
            phone = user[2] if user[2] and user[2] != "None" else "None"
            name = user[3] if user[3] and user[3] != "None" else "None"
            
            response += (
                f"👤 *Nome:* {escape_markdown(name)}\n"
                f"📱 *Telefone:* {escape_markdown(phone)}\n"
                f"🆔 *ID:* {user_id}\n"
                f"🔗 *Username:* {escape_markdown(username)}\n"
                f"────────────────────\n"
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]]
        await query.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "reg_pagamentos":
        cursor.execute("""
            SELECT id, username, telegram_id, phone_number, name, amount, proof_file_id 
            FROM payments 
            WHERE status = 'pendente'
        """)
        
        for pid, uname, uid, phone, name, amt, proof in cursor.fetchall():
            username = f"@{uname}" if uname and uname != "None" else "None"
            user_id = uid if uid else "None"
            phone = phone if phone and phone != "None" else "None"
            name = name if name and name != "None" else "None"
            
            msg = escape_markdown(
                f"💳 *PAGAMENTO PENDENTE*\n\n"
                f"👤 *Nome:* {name}\n"
                f"📱 *Telefone:* {phone}\n"
                f"🆔 *ID:* {user_id}\n"
                f"🔗 *Username:* {username}\n"
                f"💰 *Valor:* R${amt:.2f}\n"
                f"🆔 *PID:* {pid}"
            )

            keyboard = [
                [
                    InlineKeyboardButton("✅ Aprovar", callback_data=f"autorizar_{pid}"),
                    InlineKeyboardButton("❌ Recusar", callback_data=f"nao_autorizar_{pid}")
                ]
            ]
            
            try:
                await query.message.reply_photo(
                    photo=proof,
                    caption=msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Erro ao enviar comprovante: {str(e)}")
                await query.message.reply_text(
                    msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

    elif query.data == "pag_autorizados":
        cursor.execute("""
            SELECT username, telegram_id, phone_number, name, amount, proof_file_id 
            FROM payments 
            WHERE status = 'autorizado'
        """)
        
        for uname, uid, phone, name, amt, proof in cursor.fetchall():
            username = f"@{uname}" if uname and uname != "None" else "None"
            user_id = uid if uid else "None"
            phone = phone if phone and phone != "None" else "None"
            name = name if name and name != "None" else "None"
            
            msg = escape_markdown(
                f"✅ *PAGAMENTO APROVADO*\n\n"
                f"👤 *Nome:* {name}\n"
                f"📱 *Telefone:* {phone}\n"
                f"🆔 *ID:* {user_id}\n"
                f"🔗 *Username:* {username}\n"
                f"💰 *Valor:* R${amt:.2f}"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]]
            
            try:
                await query.message.reply_photo(
                    photo=proof,
                    caption=msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Erro ao enviar comprovante aprovado: {str(e)}")
                await query.message.reply_text(
                    msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

    elif query.data == "pag_nao_autorizados":
        cursor.execute("""
            SELECT username, telegram_id, phone_number, name, amount, proof_file_id 
            FROM payments 
            WHERE status = 'nao_autorizado'
        """)
        
        for uname, uid, phone, name, amt, proof in cursor.fetchall():
            username = f"@{uname}" if uname and uname != "None" else "None"
            user_id = uid if uid else "None"
            phone = phone if phone and phone != "None" else "None"
            name = name if name and name != "None" else "None"
            
            msg = escape_markdown(
                f"❌ *PAGAMENTO RECUSADO*\n\n"
                f"👤 *Nome:* {name}\n"
                f"📱 *Telefone:* {phone}\n"
                f"🆔 *ID:* {user_id}\n"
                f"🔗 *Username:* {username}\n"
                f"💰 *Valor:* R${amt:.2f}"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]]
            
            try:
                await query.message.reply_photo(
                    photo=proof,
                    caption=msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Erro ao enviar comprovante recusado: {str(e)}")
                await query.message.reply_text(
                    msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

    elif query.data == "saldo_ativo":
        cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'autorizado'")
        total_ativo = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'nao_autorizado'")
        total_inativo = cursor.fetchone()[0] or 0

        # Formata a mensagem e ESCAPA os caracteres especiais do MarkdownV2
        msg = escape_markdown(
            f"📊 *RESUMO FINANCEIRO*\n\n"
            f"✅ Total Aprovado: R$ {total_ativo:.2f}\n"
            f"❌ Total Recusado: R$ {total_inativo:.2f}"
        )

        keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]]
        await query.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


    elif query.data == "saldo_inativo":
        cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'nao_autorizado'")
        total = cursor.fetchone()[0] or 0
        
        keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]]
        await query.message.reply_text(
            f"💰 *Saldo Ativo Total:* R${total:.2f}", 
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "voltar_menu":
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Não foi possível deletar mensagem: {e}")
    
        await registros(update, context)

# ================= MAIN =======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pay", pay))
    app.add_handler(CommandHandler("registros", registros))
    app.add_handler(CommandHandler("limpar", limpar))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(button, pattern=r"^(enviar_comprovante|autorizar_\d+|nao_autorizar_\d+)$"))
    app.add_handler(CallbackQueryHandler(registros_callback))
    
    # Mensagens
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("🤖 Bot iniciado com sucesso!")
    app.run_polling()

if __name__ == "__main__":
    main()
