import os
import telebot
import random
from pymongo import MongoClient, errors
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Load environment variables for sensitive information
API_TOKEN = os.getenv("API_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# MongoDB Connection
try:
    client = MongoClient(MONGO_URI)
    db = client['philo_grabber']  # Database name
    users_collection = db['users']  # Collection for user data
    characters_collection = db['characters']  # Collection for character data
    groups_collection = db['groups']  # Collection for group stats
    print("✅ Connected to MongoDB")
except errors.ServerSelectionTimeoutError as err:
    print(f"Error: Could not connect to MongoDB: {err}")
    exit()

SUDO_USERS = [7222795580, 6180999156]

bot = telebot.TeleBot(API_TOKEN)

BONUS_COINS = 50000
BONUS_INTERVAL = timedelta(days=1)
COINS_PER_GUESS = 50
STREAK_BONUS_COINS = 1000

# Updated Rarity Levels with New Categories and Emojis
RARITY_LEVELS = {
    'Bronze': '🥉',
    'Silver': '🥈',
    'Gold': '🥇',
    'Platinum': '💿',
    'Diamond': '💎'
}
RARITY_WEIGHTS = [60, 25, 10, 4, 1]  # Adjusted weights for new rarities
MESSAGE_THRESHOLD = 5  # Default number of messages before sending a new character
TOP_LEADERBOARD_LIMIT = 10

# Level-Up System Configuration
XP_PER_CORRECT_GUESS = 100
XP_PER_BONUS_CLAIM = 50
LEVEL_UP_XP_BASE = 500
LEVEL_UP_XP_INCREMENT = 150

def is_sudo(user_id):
    return user_id in SUDO_USERS

# Helper function for calculating level and XP threshold
def calculate_level_and_xp(user_xp):
    level = 1
    xp_threshold = LEVEL_UP_XP_BASE
    while user_xp >= xp_threshold:
        user_xp -= xp_threshold
        level += 1
        xp_threshold += LEVEL_UP_XP_INCREMENT
    return level, xp_threshold - user_xp

# Function to assign rarity based on defined weights
def assign_rarity():
    return random.choices(list(RARITY_LEVELS.keys()), weights=RARITY_WEIGHTS, k=1)[0]

# Global variables to track the current character and message count
current_character = None
global_message_count = 0

def get_user_data(user_id):
    user = users_collection.find_one({'user_id': user_id})
    if user is None:
        new_user = {
            'user_id': user_id,
            'coins': 0,
            'correct_guesses': 0,
            'xp': 0,
            'last_bonus': None,
            'streak': 0,
            'profile': None
        }
        users_collection.insert_one(new_user)
        return new_user
    return user

def update_user_data(user_id, update_data):
    users_collection.update_one({'user_id': user_id}, {'$set': update_data})

# Helper function to update character IDs sequentially
def update_character_ids():
    characters = list(characters_collection.find().sort("id"))
    for index, character in enumerate(characters):
        new_id = index + 1
        if character["id"] != new_id:
            characters_collection.update_one({"_id": character["_id"]}, {"$set": {"id": new_id}})

# Function to handle XP and potential level-up
def handle_level_up(user_id, xp_gained):
    user = get_user_data(user_id)
    new_xp = user['xp'] + xp_gained
    level_before, _ = calculate_level_and_xp(user['xp'])
    level_after, xp_to_next_level = calculate_level_and_xp(new_xp)

    update_user_data(user_id, {'xp': new_xp})

    if level_after > level_before:
        return level_after, xp_to_next_level
    else:
        return None, xp_to_next_level

# Function to shuffle and send a random character
def send_character(chat_id):
    global current_character
    characters = list(characters_collection.find())
    if characters:
        current_character = random.choice(characters)  # Shuffle and pick a random character
        rarity = RARITY_LEVELS[current_character['rarity']]
        caption = (
            f"🎨 Guess the Anime Character!\n\n"
            f"💬 Name: ???\n"
            f"✨ Rarity: {rarity} {current_character['rarity']}\n"
        )
        try:
            bot.send_photo(chat_id, current_character['image_url'], caption=caption)
        except Exception as e:
            print(f"Error sending character image: {e}")
            bot.send_message(chat_id, "❌ Unable to send character image.")
    else:
        bot.send_message(chat_id, "⚠️ No characters available to display.")

# Message handler for character guessing and message counting
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    global global_message_count
    global current_character
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_guess = message.text.strip().lower() if message.text else ""

    # Increment message count if in a group or supergroup
    if message.chat.type in ['group', 'supergroup']:
        global_message_count += 1

    # Send a shuffled character if message threshold is met
    if global_message_count >= MESSAGE_THRESHOLD:
        send_character(chat_id)
        global_message_count = 0

    # Check for correct guess if there's a current character to guess
    if current_character and user_guess:
        character_name = current_character['character_name'].strip().lower()

        if user_guess in character_name:
            # Correct guess detected
            user = get_user_data(user_id)
            new_coins = user['coins'] + COINS_PER_GUESS
            user['correct_guesses'] += 1
            user['streak'] += 1
            streak_bonus = STREAK_BONUS_COINS * user['streak']

            # Update user data with new coins, streak, and correct guesses
            update_user_data(user_id, {
                'coins': new_coins + streak_bonus,
                'correct_guesses': user['correct_guesses'],
                'streak': user['streak']
            })

            # Handle XP and potential level-up
            level_up, xp_to_next_level = handle_level_up(user_id, XP_PER_CORRECT_GUESS)

            # Send congratulatory message
            response = (f"🎉 Congratulations! You guessed correctly and earned {COINS_PER_GUESS} coins!\n"
                        f"🔥 Streak Bonus: {streak_bonus} coins for a {user['streak']}-guess streak!\n"
                        f"🌟 You earned {XP_PER_CORRECT_GUESS} XP.")
            if level_up:
                response += f"\n🏆 Congratulations! You've leveled up to Level {level_up}!"
            else:
                response += f"\n📈 XP to next level: {xp_to_next_level}"

            bot.reply_to(message, response)

            # Send a new character after a correct guess
            send_character(chat_id)
            current_character = None  # Reset current character after a correct guess

# Start polling
bot.infinity_polling(timeout=60, long_polling_timeout=60)
