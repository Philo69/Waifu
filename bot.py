import time
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
import config
import numpy as np

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection with error handling
mongo_connected = False
try:
    client = MongoClient(config.MONGO_URI)
    db = client["AnimeGameDB"]
    characters_collection = db["characters"]
    user_collection = db["users"]
    mongo_connected = True
    logger.info("MongoDB connected successfully.")
except Exception as e:
    logger.error("Failed to connect to MongoDB", exc_info=True)


class AnimeGuessingGame:
    def __init__(self):
        self.selected_character = None
        self.hint_index = 0
        self.sudo_users = set()

    def start_game(self):
        self.selected_character = self.get_random_character()
        self.hint_index = 0

    def get_random_character(self):
        try:
            character = characters_collection.aggregate([{"$sample": {"size": 1}}]).next()
            return character
        except Exception as e:
            logger.error("Error fetching character from MongoDB", exc_info=True)
            return None

    def get_hint(self):
        name = self.selected_character["name"]
        hint = name[:self.hint_index + 1] + "_" * (len(name) - self.hint_index - 1)
        self.hint_index += 1
        return hint

    def guess_character(self, user_id, guess):
        character_name = self.selected_character["name"].lower()
        if guess.lower() == character_name:
            user_info = self.get_or_create_user(user_id)
            reward = user_info["level"] * config.COINS_PER_GUESS
            user_info["coins"] += reward
            user_info["level"] += 1
            user_info["guess_count"] += 1
            self.save_user_data(user_id, user_info)

            if user_info["guess_count"] >= config.MESSAGE_THRESHOLD:
                user_info["guess_count"] = 0
                self.save_user_data(user_id, user_info)
                return True, reward, "threshold_reached"
            return True, reward, "continue"
        else:
            return False, self.get_hint()

    def get_or_create_user(self, user_id):
        try:
            user = user_collection.find_one({"user_id": user_id})
            if not user:
                user = {"user_id": user_id, "coins": 0, "level": 1, "guess_count": 0}
                user_collection.insert_one(user)
            return user
        except Exception as e:
            logger.error("Error retrieving or creating user", exc_info=True)
            return {"user_id": user_id, "coins": 0, "level": 1, "guess_count": 0}

    def save_user_data(self, user_id, user_data):
        try:
            user_collection.update_one({"user_id": user_id}, {"$set": user_data})
        except Exception as e:
            logger.error("Error saving user data", exc_info=True)

    def assign_rarity(self):
        try:
            rarity = np.random.choice(list(config.RARITY_LEVELS.keys()), p=[w / 100 for w in config.RARITY_WEIGHTS])
            return rarity, config.RARITY_LEVELS[rarity]
        except Exception as e:
            logger.error("Error assigning character rarity", exc_info=True)
            return "Common", "⭐"

    def upload_character(self, character_name, user_id):
        if user_id == config.BOT_OWNER_ID or user_id in self.sudo_users:
            rarity, rarity_emoji = self.assign_rarity()
            try:
                characters_collection.insert_one({"name": character_name, "rarity": rarity, "emoji": rarity_emoji})
                return f"✅ Character '{character_name}' added successfully with rarity {rarity_emoji} ({rarity})."
            except Exception as e:
                logger.error("Error uploading character to MongoDB", exc_info=True)
                return "❌ Failed to add character to the database."
        else:
            return "❌ User does not have permission to upload characters."

    def get_leaderboard(self):
        try:
            top_users = user_collection.find().sort("coins", -1).limit(config.TOP_LEADERBOARD_LIMIT)
            leaderboard_text = "◉ 🏆 Top 10 Users 🏆 ◉\n"
            leaderboard_text += "\n".join([f"{user['user_id']}: {user['coins']} coins 💰" for user in top_users])
            return leaderboard_text
        except Exception as e:
            logger.error("Error fetching leaderboard data", exc_info=True)
            return "❌ Failed to retrieve leaderboard."

    def add_sudo_user(self, new_sudo_id, current_user_id):
        if current_user_id == config.BOT_OWNER_ID:
            self.sudo_users.add(new_sudo_id)
            return f"👑 User {new_sudo_id} has been granted sudo privileges."
        else:
            return "❌ Only the owner can add sudo users."


# Initialize the game
game = AnimeGuessingGame()

# Define Bot Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎉 Welcome to Philo Waifu! 🎉 Start guessing the character name. Type /help for commands.")

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /hello command to check bot's active status and MongoDB connection."""
    start_time = time.time()
    mongo_status = "connected" if mongo_connected else "not connected"
    ping = round((time.time() - start_time) * 1000)  # Ping in milliseconds
    await update.message.reply_text(f"👋 Bot is active!\nMongoDB is {mongo_status}.\nPing: {ping} ms.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "⌲ 📜 **Available Commands** 📜 ⌲\n"
        "/start - Start the game\n"
        "/hello - Check bot status and MongoDB connection\n"
        "/profile - View your profile\n"
        "/leaderboard - View the top players\n"
        "/upload <character_name> - Upload a new character\n"
        "/addsudo <user_id> - Grant sudo privileges\n"
        "/help - Display help message\n"
    )
    await update.message.reply_text(help_text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    try:
        user = game.get_or_create_user(user_id)
        profile_info = (
            f"◉ 👤 **Profile** 👤 ◉\n"
            f"⌲ Level: {user['level']} 🌟\n"
            f"⌲ Coins: {user['coins']} 💰\n"
            f"⌲ Guesses Left until Reset: {config.MESSAGE_THRESHOLD - user['guess_count']} 🔄"
        )
        await update.message.reply_text(profile_info)
    except Exception as e:
        logger.error("Error fetching profile", exc_info=True)
        await update.message.reply_text("❌ Failed to retrieve profile.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    leaderboard_text = game.get_leaderboard()
    await update.message.reply_text(leaderboard_text)

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /upload <character_name>")
        return
    character_name = " ".join(context.args)
    response = game.upload_character(character_name, user_id)
    await update.message.reply_text(response)

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.message.from_user.id
    try:
        new_sudo_id = int(context.args[0])
        response = game.add_sudo_user(new_sudo_id, current_user_id)
        await update.message.reply_text(response)
    except (IndexError, ValueError) as e:
        logger.error("Error processing addsudo command", exc_info=True)
        await update.message.reply_text("Usage: /addsudo <user_id>")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    guess_text = update.message.text
    if game.selected_character is None:
        await update.message.reply_text("❌ No character is currently available. Please wait for the next round.")
        return

    correct, response, status = game.guess_character(user_id, guess_text)
    if correct:
        user_info = game.get_or_create_user(user_id)
        await update.message.reply_text(f"🎉 Correct! 🎉 You've earned {response} coins. Total coins: {user_info['coins']} 💰. Level: {user_info['level']} 🌟")

        if status == "threshold_reached":
            await update.message.reply_text("🔄 Threshold reached! Here's a new character.")
        game.start_game()
        rarity_emoji = game.selected_character.get("emoji", "")
        await update.message.reply_text(f"◉ {rarity_emoji} **A new character has appeared! Start guessing!** {rarity_emoji} ◉")
    else:
        await update.message.reply_text(f"❌ Incorrect! Hint: {response}")

def main():
    application = Application.builder().token(config.API_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("hello", hello))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("upload", upload, filters=filters.User(config.BOT_OWNER_ID) | filters.User(lambda user_id: user_id in game.sudo_users)))
    application.add_handler(CommandHandler("addsudo", add_sudo, filters=filters.User(config.BOT_OWNER_ID)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess))

    application.run_polling()

if __name__ == "__main__":
    main()
