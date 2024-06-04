from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

telegram_bot_api_key = os.getenv("TELEGRAM_BOT_API_KEY")

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv('SUPABASE_DB_NAME'),
        user=os.getenv('SUPABASE_DB_USER'),
        password=os.getenv('SUPABASE_DB_PASSWORD'),
        host=os.getenv('SUPABASE_DB_HOST'),
        port=os.getenv('SUPABASE_DB_PORT')
    )

authenticated_users = {}
SEARCH_NAME = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hola {update.effective_user.first_name}, por favor ingresa la contraseña.')

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    message_text = update.message.text

    if message_text == 'misericordia':
        await update.message.reply_text('Soy Missy! Bienvenido al bot de asignaciones de la Congregación Plaza de la Misericordia.')
        authenticated_users[user_id] = True
    else:
        await update.message.reply_text('Contraseña incorrecta. Inténtalo nuevamente.')
        authenticated_users[user_id] = False

async def obtener_reuniones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await obtener_reuniones_actual(update, context, 0)

async def obtener_reuniones_siguiente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await obtener_reuniones_actual(update, context, 1)

async def obtener_reuniones_actual(update: Update, context: ContextTypes.DEFAULT_TYPE, semana_offset: int) -> None:
    user_id = update.message.from_user.id
    if authenticated_users.get(user_id, False):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT reuniones.fecha, reuniones.sala, 
                   asignaciones.nombre_asign AS Asignacion, 
                   hermanos_titular.nombre_hermano || ' ' || hermanos_titular.apellido_hermano AS Titular, 
                   CASE WHEN reuniones.ayudante IS NULL THEN ' ' ELSE hermanos_suplente.nombre_hermano || ' ' || hermanos_suplente.apellido_hermano END AS Ayudante 
            FROM reuniones 
            INNER JOIN asignaciones ON reuniones.id_Asign = asignaciones.id_asign 
            INNER JOIN hermanos AS Hermanos_titular ON reuniones.id_hermano = Hermanos_titular.id_hermano 
            LEFT JOIN hermanos AS Hermanos_suplente ON reuniones.ayudante = Hermanos_suplente.id_hermano
        ''')
        reuniones = cursor.fetchall()
        conn.close()

        today = datetime.now()
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=semana_offset)
        next_monday = monday + timedelta(days=7)

        monday_date = monday.date()
        next_monday_date = next_monday.date()

        filtered_reuniones = [
            {
                'Fecha': reunion[0],
                'Sala': reunion[1],
                'Asignacion': reunion[2],
                'Titular': reunion[3],
                'Ayudante': reunion[4]
            }
            for reunion in reuniones
            if monday_date <= reunion[0] < next_monday_date
        ]

        if not filtered_reuniones:
            await update.message.reply_text('No hay reuniones programadas para esa semana.')
            return

        message_text = ""
        first_reunion_date = filtered_reuniones[0].get('Fecha', '')
        if first_reunion_date:
            message_text += f"*Reunión de la semana {first_reunion_date}\n*"

        for reunion in filtered_reuniones:
            details = []
            if reunion.get('Asignacion'):
                details.append(f"*{reunion['Asignacion']}:*")
            if reunion.get('Sala'):
                details.append(f"*Sala {reunion['Sala']}* -")
            if reunion.get('Titular'):
                details.append(f"{reunion['Titular']}")
            if reunion.get('Ayudante') and reunion['Ayudante'].strip() and reunion['Ayudante'].strip().lower() != 'no aplica':
                details.append(f"*Ayudante: {reunion['Ayudante']}*")

            if details:
                message_text += " ".join(details) + "\n"

        await update.message.reply_text(message_text, parse_mode='Markdown')         
    else:
        await update.message.reply_text('No estás autorizado para usar este comando. Por favor, introduce la contraseña correcta primero.')

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if authenticated_users.get(user_id, False):
        await update.message.reply_text('Por favor, ingresa el nombre de la persona que deseas buscar.')
        return SEARCH_NAME
    else:
        await update.message.reply_text('No estás autorizado para usar este comando. Por favor, introduce la contraseña correcta primero.')
        return ConversationHandler.END
async def resultado_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if authenticated_users.get(user_id, False):
        nombre_buscar = update.message.text

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT reuniones.fecha, reuniones.sala, 
                   asignaciones.nombre_asign AS Asignacion, 
                   hermanos_titular.nombre_hermano || ' ' || hermanos_titular.apellido_hermano AS Titular, 
                   CASE WHEN reuniones.ayudante IS NULL THEN ' ' ELSE hermanos_suplente.nombre_hermano || ' ' || hermanos_suplente.apellido_hermano END AS Ayudante 
            FROM reuniones 
            INNER JOIN asignaciones ON reuniones.id_Asign = asignaciones.id_asign 
            INNER JOIN hermanos AS Hermanos_titular ON reuniones.id_hermano = Hermanos_titular.id_hermano 
            LEFT JOIN hermanos AS Hermanos_suplente ON reuniones.ayudante = Hermanos_suplente.id_hermano
            WHERE (hermanos_titular.nombre_hermano || ' ' || hermanos_titular.apellido_hermano ILIKE %s
               OR hermanos_suplente.nombre_hermano || ' ' || hermanos_suplente.apellido_hermano ILIKE %s)
               AND reuniones.fecha >= CURRENT_DATE
        ''', (f'%{nombre_buscar}%', f'%{nombre_buscar}%'))
        reuniones = cursor.fetchall()
        conn.close()

        if not reuniones:
            await update.message.reply_text(f'No se encontraron reuniones para {nombre_buscar}.')
            return ConversationHandler.END

        message_text = f'Asignaciones para *{nombre_buscar}*:\n'
        for reunion in reuniones:
            details = [f"*Fecha:* {reunion[0].strftime('%Y-%m-%d')}", f"*Asignación:* {reunion[2]}", f"*Titular:* {reunion[3]}"]
            if reunion[1] and reunion[1].strip().lower() != 'none':
                details.append(f"*Sala:* {reunion[1]}")
            if reunion[4].strip() and reunion[4].strip().lower() != 'no aplica':
                details.append(f"*Ayudante:* {reunion[4]}")
            message_text += "\n".join(details) + "\n\n"

        await update.message.reply_text(message_text, parse_mode='Markdown')
        return ConversationHandler.END

    else:
        await update.message.reply_text('No estás autorizado para usar este comando. Por favor, introduce la contraseña correcta primero.')
        return ConversationHandler.END


# Configuración del bot y manejadores de comandos
if __name__ == '__main__':
    app = ApplicationBuilder().token(telegram_bot_api_key).build()

    # Configuración del ConversationHandler para el comando "buscar"
    buscar_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar)],
        states={
            SEARCH_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, resultado_busqueda)]
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reunion", obtener_reuniones))
    app.add_handler(CommandHandler("siguiente", obtener_reuniones_siguiente))
    app.add_handler(buscar_handler)  # Agrega buscar_handler en lugar de resultado_busqueda
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_password))
    app.run_polling()