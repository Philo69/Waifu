import telebot
import random
from pymongo import MongoClient, errors
from datetime import datetime, timedelta

# Bot API token and MongoDB connection URI
API_TOKEN = "6862816736:AAGAAsqsz7MzO6uSMfIbkjt1NScwtC6mITU"
MONGO_URI = "mongodb+srv://PhiloWise:Philo@waifu.yl9tohm.mongodb.net/?retryWrites=true&w=majority&appName=Waifu"

# Bot Owner and Channel IDs
BOT_OWNER_ID = 7222795580  # Specified owner ID
CHARACTER_CHANNEL_ID = -1002438449944

# Game Settings
BONUS_COINS = 50000               # Daily bonus coins for /bonus command
STREAK_BONUS_COINS = 1000         # Additional coins for maintaining a streak
BONUS_INTERVAL = timedelta(days=1) # Time interval for claiming daily bonus

COINS_PER_GUESS = 50              # Coins awarded for a correct guess
MESSAGE_THRESHOLD = 5             # Messages needed in group to trigger character appearance
TOP_LEADERBOARD_LIMIT = 10        # Limit for the top leaderboard display

# Character Rarity Settings
RARITY_LEVELS = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']
RARITY_EMOJIS = ['🥉', '🥈', '🥇', '🏆', '💎']
RARITY_WEIGHTS = [40, 30, 15, 10, 5]
RARITY_DICT = dict(zip(RARITY_LEVELS, RARITY_EMOJIS))

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

SUDO_USERS = [BOT_OWNER_ID]  # List of sudo users, starting with the bot owner

bot = telebot.TeleBot(API_TOKEN)

# Global variables to track the current character and message count
current_character = None
global_message_count = 0

def get_user_data(user_id):
    try:
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
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return None

def update_user_data(user_id, update_data):
    try:
        users_collection.update_one({'user_id': user_id}, {'$set': update_data})
    except Exception as e:
        print(f"Error updating user data: {e}")

def calculate_level_and_xp(user_xp):
    level = 1
    xp_threshold = 500
    increment = 150
    while user_xp >= xp_threshold:
        user_xp -= xp_threshold
        level += 1
        xp_threshold += increment
    return level, xp_threshold - user_xp

def handle_level_up(user_id, xp_gained):
    user = get_user_data(user_id)
    if user is None:
        return None, None

    new_xp = user['xp'] + xp_gained
    level_before, _ = calculate_level_and_xp(user['xp'])
    level_after, xp_to_next_level = calculate_level_and_xp(new_xp)

    update_user_data(user_id, {'xp': new_xp})

    if level_after > level_before:
        return level_after, xp_to_next_level  # Level-up occurred
    else:
        return None, xp_to_next_level

def assign_rarity():
    return random.choices(RARITY_LEVELS, weights=RARITY_WEIGHTS, k=1)[0]

def fetch_random_character():
    characters = list(characters_collection.find())
    if characters:
        return random.choice(characters)
    return None

def send_character(chat_id):
    global current_character
    current_character = fetch_random_character()
    if current_character:
        rarity = RARITY_DICT[current_character['rarity']]
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    if user is None:
        bot.reply_to(message, "Error initializing user data.")
        return

    if not user['profile']:
        profile_name = message.from_user.full_name
        update_user_data(user_id, {'profile': profile_name})

    welcome_message = """
<b>🌸 Welcome to Philo Waifu 🌸</b>

🎉 Get ready to dive into the world of anime characters! With Philo Waifu, you can:
- 🏆 Guess anime characters to earn coins, gain XP, and level up.
- 💰 Collect daily bonuses and climb the leaderboard.
- 🤔 Simply type your guess; if any word matches a character's name, you score!

Use /help to see all available commands. Let's start your anime adventure!
"""
    bot.send_message(message.chat.id, welcome_message, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def show_help(message):
    help_message = """
<b>🌸 Philo Waifu Bot Commands 🌸</b>

<b>General Commands:</b>
/start - Start the bot and get a welcome message.
/help - Show this help message listing all available commands.
/bonus - Claim your daily bonus coins and XP.
/profile - View your profile, including your level, XP, and coins.
/leaderboard - Show the top 10 users with their levels and coins.
/stats - View bot statistics (Owner only).

<b>Sudo Commands:</b> (For bot owners and sudo users)
/upload <img_url> <character_name> - Add a new character with an image URL and character name.
/delete <id> - Delete a character by its ID.
/addsudo <user_id> - Add a new sudo user (Owner only).
/changetime <interval> - Change the message threshold for character appearance.
"""
    bot.send_message(message.chat.id, help_message, parse_mode='HTML')

@bot.message_handler(commands=['profile'])
def show_profile(message):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    if user is None:
        bot.reply_to(message, "Error fetching profile data.")
        return

    level, xp_to_next_level = calculate_level_and_xp(user['xp'])
    profile_message = (
        f"<b>🌸 Profile of {user['profile'] or 'User'}</b>\n\n"
        f"💠 Level: {level}\n"
        f"🌟 XP: {user['xp']} (Next level in {xp_to_next_level} XP)\n"
        f"💰 Coins: {user['coins']}\n"
        f"🔥 Streak: {user['streak']} days\n"
    )
    bot.send_message(message.chat.id, profile_message, parse_mode='HTML')

@bot.message_handler(commands=['bonus'])
def claim_bonus(message):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    if user is None:
        bot.reply_to(message, "Error fetching user data.")
        return

    current_time = datetime.now()
    if user['last_bonus']:
        time_since_last_bonus = current_time - user['last_bonus']
        if time_since_last_bonus < BONUS_INTERVAL:
            time_remaining = BONUS_INTERVAL - time_since_last_bonus
            hours, remainder = divmod(time_remaining.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            bot.reply_to(message, f"⏰ You've already claimed your bonus today! Come back in {hours} hours and {minutes} minutes.")
            return

    new_coins = user['coins'] + BONUS_COINS
    user['streak'] += 1
    streak_bonus = STREAK_BONUS_COINS * user['streak']

    update_user_data(user_id, {
        'coins': new_coins + streak_bonus,
        'last_bonus': current_time,
        'streak': user['streak']
    })

    level_up, xp_to_next_level = handle_level_up(user_id, BONUS_COINS)

    response = (f"🎁 You have claimed your daily bonus of {BONUS_COINS} coins! 🎉\n"
                f"🔥 Streak Bonus: {streak_bonus} coins for a {user['streak']}-day streak!\n"
                f"🌟 You earned {BONUS_COINS} XP.")
    if level_up:
        response += f"\n🏆 Congratulations! You've leveled up to Level {level_up}!"
    else:
        response += f"\n📈 XP to next level: {xp_to_next_level}"

    bot.reply_to(message, response)

@bot.message_handler(commands=['leaderboard'])
def show_leaderboard(message):
    try:
        top_users = users_collection.find().sort('coins', -1).limit(TOP_LEADERBOARD_LIMIT)
        leaderboard_message = "<b>🏆 Leaderboard</b>\n\n"
        for i, user in enumerate(top_users, start=1):
            level, _ = calculate_level_and_xp(user['xp'])
            leaderboard_message += (
                f"{i}. {user['profile'] or 'User'}\n"
                f"   💰 Coins: {user['coins']} | 💠 Level: {level}\n"
            )
        bot.send_message(message.chat.id, leaderboard_message, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, "Error fetching leaderboard.")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id != BOT_OWNER_ID:
        bot.reply_to(message, "🚫 You don't have permission to use this command.")
        return

    try:
        total_users = users_collection.count_documents({})
        total_characters = characters_collection.count_documents({})
        total_groups = groups_collection.count_documents({})

        stats_message = (
            f"<b>📊 Bot Statistics:</b>\n\n"
            f"👤 Total Users: {total_users}\n"
            f"🎎 Total Characters: {total_characters}\n"
            f"💬 Total Groups: {total_groups}\n"
        )
        bot.send_message(message.chat.id, stats_message, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, "Error fetching stats.")

@bot.message_handler(commands=['addsudo'])
def add_sudo_user(message):
    if message.from_user.id != BOT_OWNER_ID:
        bot.reply_to(message, "🚫 You don't have permission to use this command.")
        return

    try:
        command_args = message.text.split(maxsplit=1)
        if len(command_args) < 2:
            bot.reply_to(message, "⚠️ Usage: /addsudo <user_id>")
            return

        new_sudo_user_id = int(command_args[1])
        if new_sudo_user_id not in SUDO_USERS:
            SUDO_USERS.append(new_sudo_user_id)
            bot.reply_to(message, f"✅ User {new_sudo_user_id} has been added as a sudo user.")
        else:
            bot.reply_to(message, "⚠️ User is already a sudo user.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID format.")
    except Exception as e:
        bot.reply_to(message, "⚠️ An error occurred while adding sudo user.")

@bot.message_handler(commands=['upload'])
def upload_character(message):
    if message.from_user.id not in SUDO_USERS:
        bot.reply_to(message, "🚫 You don't have permission to use this command.")
        return

    try:
        command_args = message.text.split(maxsplit=2)
        if len(command_args) < 3:
            bot.reply_to(message, "⚠️ Usage: /upload <img_url> <character_name>")
            return

        img_url = command_args[1]
        character_name = command_args[2]
        rarity = assign_rarity()

        new_character = {
            'image_url': img_url,
            'character_name': character_name,
            'rarity': rarity
        }
        characters_collection.insert_one(new_character)

        bot.reply_to(message, f"✅ Character '{character_name}' with rarity '{RARITY_DICT[rarity]} {rarity}' uploaded successfully!")
    except Exception as e:
        bot.reply_to(message, "⚠️ An error occurred while uploading the character.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    global global_message_count
    global current_character
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_guess = message.text.strip().lower() if message.text else ""

    if message.chat.type in ['group', 'supergroup']:
        global_message_count += 1

    if global_message_count >= MESSAGE_THRESHOLD:
        send_character(chat_id)
        global_message_count = 0

    if current_character and user_guess:
        character_words = set(current_character['character_name'].strip().lower().split())
        guess_words = set(user_guess.split())

        if character_words & guess_words:
            user = get_user_data(user_id)
            if user is None:
                bot.reply_to(message, "Error fetching user data.")
                return

            new_coins = user['coins'] + COINS_PER_GUESS
            user['correct_guesses'] += 1
            user['streak'] += 1
            streak_bonus = STREAK_BONUS_COINS * user['streak']
            
            update_user_data(user_id, {
                'coins': new_coins + streak_bonus,
                'correct_guesses': user['correct_guesses'],
                'streak': user['streak']
            })

            level_up, xp_to_next_level = handle_level_up(user_id, COINS_PER_GUESS)

            response = (f"🎉 Congratulations! You guessed correctly and earned {COINS_PER_GUESS} coins!\n"
                        f"🔥 Streak Bonus: {streak_bonus} coins for a {user['streak']}-guess streak!\n"
                        f"🌟 You earned {COINS_PER_GUESS} XP.")
            if level_up:
                response += f"\n🏆 Congratulations! You've leveled up to Level {level_up}!"
            else:
                response += f"\n📈 XP to next level: {xp_to_next_level}"

            bot.reply_to(message, response)
            
            send_character(chat_id)
            current_character = None

bot.infinity_polling(timeout=60, long_polling_timeout=60)
