import os
import logging
import random
import uuid
import html
import requests
from datetime import datetime, timedelta
from threading import Thread

from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, PollAnswerHandler, CallbackQueryHandler
)
from replit import db
from flask import Flask, request as flask_request

# --- Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get secrets from Replit's environment variables (Secrets tab)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAPA_SECRET_KEY = os.getenv('CHAPA_SECRET_KEY')
ADMIN_TELEGRAM_ID = os.getenv('ADMIN_TELEGRAM_ID')

# Bot settings
DAILY_QUESTION_LIMIT = 10
PREMIUM_PRICE = 100  # ETB
PAYOUT_THRESHOLD = 5000  # ETB
PRIZE_POOL_PERCENTAGE = 0.30  # 30%

# --- Ethiopian Trivia Questions (Our local list) ---
ETHIOPIAN_QUESTIONS = [
    {'question': 'What is the capital city of Ethiopia?', 'options': ['Bahir Dar', 'Addis Ababa', 'Mekelle', 'Hawassa'], 'correct_option_id': 1},
    {'question': 'Which is the largest river in Ethiopia?', 'options': ['Omo River', 'Awash River', 'Blue Nile', 'Tekeze River'], 'correct_option_id': 2},
    {'question': 'In which year was the Battle of Adwa fought?', 'options': ['1888', '1902', '1896', '1935'], 'correct_option_id': 2},
    {'question': 'What is the main ingredient in the traditional dish "Injera"?', 'options': ['Barley', 'Corn', 'Teff Flour', 'Wheat'], 'correct_option_id': 2},
    {'question': 'The rock-hewn churches of Lalibela are in which region?', 'options': ['Tigray', 'Oromia', 'Amhara', 'SNNPR'], 'correct_option_id': 2},
    {'question': 'Which Ethiopian emperor is a central figure in the Rastafari movement?', 'options': ['Menelik II', 'Tewodros II', 'Yohannes IV', 'Haile Selassie I'], 'correct_option_id': 3},
    {'question': 'Coffee is believed to have originated in which Ethiopian region?', 'options': ['Harar', 'Sidamo', 'Yirgacheffe', 'Kaffa'], 'correct_option_id': 3},
    {'question': 'What is the official currency of Ethiopia?', 'options': ['Dollar', 'Shilling', 'Birr', 'Nakfa'], 'correct_option_id': 2},
    {'question': 'Which ancient kingdom had its capital at Axum?', 'options': ['Kingdom of Kush', 'Kingdom of Aksum', 'Zagwe Dynasty', 'Gondarine period'], 'correct_option_id': 1},
    {'question': 'The Simien Mountains are home to which unique primate?', 'options': ['Chimpanzee', 'Gorilla', 'Lemur', 'Gelada Baboon'], 'correct_option_id': 3},
]

# --- API & Question Handling ---
def format_api_question(api_question):
    """Converts a question from the API into our standard format."""
    options = api_question['incorrect_answers'] + [api_question['correct_answer']]
    random.shuffle(options)
    correct_option_id = options.index(api_question['correct_answer'])
    # Decode HTML entities like &quot; to "
    return {
        'question': html.unescape(api_question['question']),
        'options': [html.unescape(opt) for opt in options],
        'correct_option_id': correct_option_id
    }

def get_new_quiz_questions():
    """Fetches new questions from API and mixes them with local Ethiopian questions."""
    # 3 Ethiopian questions + 7 Worldwide questions = 10 total
    ethiopian_part = random.sample(ETHIOPIAN_QUESTIONS, 3)
    worldwide_part = []
    
    try:
        # Fetch 7 new worldwide questions from the Open Trivia Database API
        response = requests.get('https://opentdb.com/api.php?amount=7&type=multiple')
        response.raise_for_status()
        api_data = response.json()
        if api_data['response_code'] == 0:
            worldwide_part = [format_api_question(q) for q in api_data['results']]
    except requests.exceptions.RequestException as e:
        logger.error(f"Could not fetch from trivia API: {e}")
        # Fallback: use more Ethiopian questions if API fails
        return random.sample(ETHIOPIAN_QUESTIONS, 10)

    quiz = ethiopian_part + worldwide_part
    random.shuffle(quiz)
    return quiz

# --- Database Helper Functions ---
def init_user(user_id, username):
    """Initializes a new user in the database."""
    if f"user_{user_id}" not in db:
        db[f"user_{user_id}"] = {
            "username": username, "is_premium": False, "premium_expiry": None,
            "score": 0, "last_quiz_date": None, "current_quiz": [], "current_question_index": 0
        }
        db["total_users"] = db.get("total_users", 0) + 1

def get_user_data(user_id):
    return db.get(f"user_{user_id}")

def set_user_data(user_id, data):
    db[f"user_{user_id}"] = data

# --- Chapa Payment Integration ---
def generate_chapa_link(user_id, username, bot_username):
    """Generates a Chapa payment link for a user."""
    tx_ref = f"trivia-bot-{user_id}-{uuid.uuid4()}"
    webhook_url = f"https://{os.environ.get('REPL_SLUG')}.{os.environ.get('REPL_OWNER')}.replit.dev/chapa_webhook"
    headers = {"Authorization": f"Bearer {CHAPA_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "amount": str(PREMIUM_PRICE), "currency": "ETB", "email": "user@example.com",
        "first_name": username, "last_name": "Player", "tx_ref": tx_ref,
        "callback_url": webhook_url, "return_url": f"https://t.me/{bot_username}",
        "customization[title]": "Trivia Bot Premium", "customization[description]": "1 Month Premium Access"
    }
    db[f"tx_{tx_ref}"] = {"user_id": user_id, "status": "pending"}
    try:
        response = requests.post("https://api.chapa.co/v1/transaction/initialize", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("checkout_url")
    except requests.exceptions.RequestException as e:
        logger.error(f"Chapa API Error: {e}")
    return None

# --- Telegram Command & Button Handlers ---
def start_command(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
    user = update.effective_user
    init_user(user.id, user.username or user.first_name)
    keyboard = [
        [InlineKeyboardButton("Play Daily Trivia 🎲", callback_data='play_trivia')],
        [InlineKeyboardButton("Go Premium ✨", callback_data='go_premium')],
        [InlineKeyboardButton("View Leaderboard 🏆", callback_data='leaderboard')],
    ]
    update.message.reply_html(
        f"👋 Welcome, {user.mention_html()}!\n\nI'm your Trivia Bot. Test your knowledge daily.\n\n"
        "Want to compete for prizes? <b>Go Premium</b> to get on the leaderboard!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def admin_command(update: Update, context: CallbackContext) -> None:
    """Handles the /admin command."""
    if str(update.effective_user.id) != ADMIN_TELEGRAM_ID:
        update.message.reply_text("⛔️ You are not authorized.")
        return
    total_users = db.get("total_users", 0)
    total_revenue = db.get("total_gross_revenue", 0)
    premium_users = sum(1 for key in db.prefix("user_") if db[key].get("is_premium"))
    keyboard = [
        [InlineKeyboardButton("Check Prize Pool", callback_data='admin_check_payout')],
        [InlineKeyboardButton("View Leaderboard (Admin)", callback_data='admin_leaderboard')]
    ]
    update.message.reply_html(
        f"<b>⚙️ Admin Dashboard</b>\n\n<b>Users:</b> {total_users}\n<b>Premium:</b> {premium_users}\n"
        f"<b>Gross Revenue:</b> {total_revenue:.2f} ETB\n<b>Payout Threshold:</b> {PAYOUT_THRESHOLD} ETB",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def button_handler(update: Update, context: CallbackContext) -> None:
    """Handles all inline button presses."""
    query = update.callback_query
    query.answer()
    actions = {
        'play_trivia': send_question, 'go_premium': show_premium_options, 'leaderboard': show_leaderboard,
        'admin_check_payout': lambda u, c: check_payout(u, c, admin_triggered=True),
        'admin_leaderboard': lambda u, c: show_leaderboard(u, c, admin_view=True)
    }
    if query.data in actions:
        actions[query.data](update, context)

def show_premium_options(update: Update, context: CallbackContext) -> None:
    """Shows the premium subscription button."""
    query = update.callback_query
    user = query.from_user
    payment_link = generate_chapa_link(user.id, user.username or user.first_name, context.bot.username)
    if payment_link:
        keyboard = [[InlineKeyboardButton("Pay with Chapa 💳", url=payment_link)]]
        query.edit_message_text(
            f"<b>✨ Go Premium! ✨</b>\n\nGet on the leaderboard for just <b>{PREMIUM_PRICE} ETB/month</b>.\n\n"
            "Click below to pay securely. You'll be upgraded automatically!",
            parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        query.edit_message_text("Sorry, the payment service is unavailable. Please try again later.")

def send_question(update: Update, context: CallbackContext) -> None:
    """Manages the quiz session and sends the next question."""
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Start a new quiz if it's a new day or the quiz is finished/empty
    if user_data.get("last_quiz_date") != today or not user_data.get("current_quiz"):
        user_data["last_quiz_date"] = today
        user_data["current_question_index"] = 0
        user_data["current_quiz"] = get_new_quiz_questions()
    
    index = user_data["current_question_index"]
    quiz = user_data["current_quiz"]

    if index >= len(quiz) or index >= DAILY_QUESTION_LIMIT:
        query.edit_message_text("You have answered all your questions for today. Come back tomorrow! 🕒")
        user_data["current_quiz"] = [] # Clear quiz when done
        set_user_data(user_id, user_data)
        return
        
    question_data = quiz[index]
    
    message = context.bot.send_poll(
        chat_id=query.message.chat_id, question=question_data['question'],
        options=question_data['options'], is_anonymous=False, type=Poll.QUIZ,
        correct_option_id=question_data['correct_option_id']
    )
    
    context.bot_data[message.poll.id] = {"user_id": user_id}
    query.edit_message_text(f"Question {index + 1} of {DAILY_QUESTION_LIMIT}:")

def poll_answer_handler(update: Update, context: CallbackContext) -> None:
    """Handles the user's answer to a quiz."""
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    
    if poll_id not in context.bot_data: return
    
    user_id = context.bot_data[poll_id]["user_id"]
    user_data = get_user_data(user_id)
    
    index = user_data["current_question_index"]
    quiz = user_data["current_quiz"]
    
    if index >= len(quiz): return

    correct_option_id = quiz[index]['correct_option_id']
    is_correct = poll_answer.option_ids[0] == correct_option_id
    
    if is_correct:
        if user_data.get("is_premium"):
            user_data["score"] = user_data.get("score", 0) + 10
        context.bot.send_message(user_id, "Correct! 🎉")
    else:
        context.bot.send_message(user_id, "Oops, that wasn't right.")
        
    user_data["current_question_index"] += 1
    set_user_data(user_id, user_data)
    
    if user_data["current_question_index"] < DAILY_QUESTION_LIMIT:
        keyboard = [[InlineKeyboardButton("Next Question ➡️", callback_data='play_trivia')]]
        context.bot.send_message(user_id, "Ready for the next one?", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        context.bot.send_message(user_id, "You've finished your daily trivia! Your score has been updated. See you tomorrow!")
        user_data["current_quiz"] = [] # Clear quiz
        set_user_data(user_id, user_data)

def show_leaderboard(update: Update, context: CallbackContext, admin_view=False) -> None:
    """Displays the top 10 premium users."""
    query = update.callback_query
    premium_users = [u for u in db.values() if isinstance(u, dict) and u.get("is_premium") and u.get("score", 0) > 0]
    sorted_users = sorted(premium_users, key=lambda x: x['score'], reverse=True)
    
    if not sorted_users:
        query.edit_message_text("The leaderboard is empty. Go premium and play to get on it!")
        return
        
    leaderboard_text = "<b>🏆 Leaderboard 🏆</b>\n\n"
    for i, user in enumerate(sorted_users[:10]):
        rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
        username = f"@{user['username']}" if user.get('username') else "A Player"
        leaderboard_text += f"{rank} {username} - {user['score']} points\n"
    if admin_view:
        leaderboard_text += "\n<i>Admin view: Usernames shown for payout.</i>"
    query.edit_message_text(leaderboard_text, parse_mode=ParseMode.HTML)

# --- Payout Logic ---
def check_payout(update: Update, context: CallbackContext, admin_triggered=False) -> None:
    """Checks revenue and processes payouts if the threshold is met."""
    total_revenue = db.get("total_gross_revenue", 0)
    if total_revenue < PAYOUT_THRESHOLD:
        if admin_triggered:
            query = update.callback_query
            query.answer(f"Threshold not met. Current: {total_revenue:.2f} ETB")
        return

    prize_pool = total_revenue * PRIZE_POOL_PERCENTAGE
    num_winners = max(1, int(total_revenue // 5000))

    all_users = {key.split('_')[1]: val for key, val in db.items() if key.startswith("user_")}
    premium_users = [(uid, udata) for uid, udata in all_users.items() if udata.get("is_premium")]
    sorted_users = sorted(premium_users, key=lambda item: item[1].get('score', 0), reverse=True)
    winners = sorted_users[:num_winners]
    
    if not winners: return

    admin_message = f"<b>🏆 Payout Triggered! 🏆</b>\n\nPrize Pool: {prize_pool:.2f} ETB\n\n"
    for i, (winner_id, winner_data) in enumerate(winners):
        prize_share = prize_pool / len(winners)
        admin_message += f"<b>Winner {i+1}:</b> @{winner_data['username']} (ID: `{winner_id}`)\n<b>Prize:</b> {prize_share:.2f} ETB\n\n"
        try:
            context.bot.send_message(
                chat_id=winner_id,
                text=f"🥳 Congratulations, @{winner_data['username']}! You are a winner!\nYou have won *{prize_share:.2f} ETB*.\nThe admin will contact you for payment.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Could not message winner {winner_id}: {e}")

    context.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=admin_message, parse_mode=ParseMode.HTML)
    
    db["total_gross_revenue"] = 0
    for uid, udata in premium_users:
        udata["score"] = 0
        set_user_data(uid, udata)

# --- Flask Webhook for Chapa ---
app = Flask(__name__)
@app.route('/chapa_webhook', methods=['POST'])
def chapa_webhook():
    try:
        event = flask_request.json
        if event and 'tx_ref' in event:
            tx_ref = event['tx_ref']
            transaction = db.get(f"tx_{tx_ref}")
            if transaction and transaction.get('status') == 'pending':
                headers = {"Authorization": f"Bearer {CHAPA_SECRET_KEY}"}
                verify_url = f"https://api.chapa.co/v1/transaction/verify/{tx_ref}"
                response = requests.get(verify_url, headers=headers)
                if response.json().get("status") == "success":
                    user_id = transaction['user_id']
                    user_data = get_user_data(user_id)
                    if user_data:
                        user_data["is_premium"] = True
                        user_data["premium_expiry"] = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
                        set_user_data(user_id, user_data)
                        
                        db["total_gross_revenue"] = db.get("total_gross_revenue", 0) + PREMIUM_PRICE
                        transaction['status'] = 'success'
                        db[f"tx_{tx_ref}"] = transaction
                        
                        updater.bot.send_message(chat_id=user_id, text="✅ Payment successful! You are now a Premium member.")
                        # check_payout can be called here if needed
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
    return "OK", 200

# --- Main Bot Setup ---
def main() -> None:
    if not all([TELEGRAM_BOT_TOKEN, CHAPA_SECRET_KEY, ADMIN_TELEGRAM_ID]):
        logger.error("FATAL: Missing secrets. Set TELEGRAM_BOT_TOKEN, CHAPA_SECRET_KEY, and ADMIN_TELEGRAM_ID.")
        return

    global updater
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    dispatcher.add_handler(PollAnswerHandler(poll_answer_handler))

    updater.start_polling()
    logger.info("Bot started...")
    
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    updater.idle()

if __name__ == "__main__":
    main()