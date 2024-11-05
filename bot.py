import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
import config  # Import settings from config.py
import numpy as np

# Initialize MongoDB client
client = MongoClient(config.MONGO_URI)
db = client["AnimeGameDB"]
characters_collection = db["characters"]
user_collection = db["users"]

class AnimeGuessingGame:
    def __init__(self):
        self.selected_character = None
        self.hint_index = 0
        self.sudo_users = set()

    def start_game(self):
        self.selected_character = self.get_random_character()
        self.hint_index = 0

    def get_random_character(self):
        character = characters_collection.aggregate([{"$sample": {"size": 1}}]).next()
        return character

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
            user_info["level"] += 1  # Increase level on correct guess
            user_info["guess_count"] += 1
            self.save_user_data(user_id, user_info)

            if user_info["guess_count"] >= config.MESSAGE_THRESHOLD:
                user_info["guess_count"] = 0  # Reset count automatically
                self.save_user_data(user_id, user_info)
                return True, reward, "threshold_reached"

            return True, reward, "continue"
        else:
            return False, self.get_hint()

    def get_or_create_user(self, user_id):
        user = user_collection.find_one({"user_id": user_id})
        if not user:
            user = {"user_id": user_id, "coins": 0, "level": 1, "guess_count": 0}
            user_collection.insert_one(user)
        return user

    def save_user_data(self, user_id, user_data):
        user_collection.update_one({"user_id": user_id}, {"$set": user_data})

    def assign_rarity(self):
        """Assign a rarity level based on predefined weights."""
        rarity = np.random.choice(list(config.RARITY_LEVELS.keys()), p=[w / 100 for w in config.RARITY_WEIGHTS])
        return rarity, config.RARITY_LEVELS[rarity]

    def upload_character(self, character_name, user_id):
        if user_id == config.BOT_OWNER_ID or user_id in self.sudo_users:
            rarity, rarity_emoji = self.assign_rarity()
            characters_collection.insert_one({"name": character_name, "rarity": rarity, "emoji": rarity_emoji})
            return f"✅ Character '{character_name}' added successfully with rarity {rarity_emoji} ({rarity}) by user {user_id}."
        else:
            return f"❌ User {user_id} does not have permission to upload new characters."

    def get_leaderboard(self):
        top_users = user_collection.find().sort("coins", -1).limit(config.TOP_LEADERBOARD_LIMIT)
        leaderboard_text = "◉ 🏆 Top 10 Users 🏆 ◉\n"
        leaderboard_text += "\n".join([f"{user['user_id']}: {user['coins']} coins 💰" for user in top_users])
        return leaderboard_text

    def add_sudo_user(self, new_sudo_id, current_user_id):
        if current_user_id == config.BOT_OWNER_ID:
            self.sudo_users.add(new_sudo_id)
            return f"👑 User {new_sudo_id} has been granted sudo privileges."
        else:
            return "❌ Only the owner can add sudo users."


# Initialize the game
game = AnimeGuessingGame()


# Handlers for Telegram Bot Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎉 Welcome to Philo Waifu! 🎉 Start guessing the character name from the image. Type /help for a list of commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "⌲ 📜 **Available Commands** 📜 ⌲\n"
        "/start - Start the game and get a welcome message\n"
        "/profile - View your profile (level and coins)\n"
        "/leaderboard - View the top 10 players\n"
        "/upload <character_name> - (Owner/Sudo only) Upload a new character without an image\n"
        "/addsudo <user_id> - (Owner only) Grant sudo privileges to a user\n"
        "/help - Display this help message\n"
    )
    await update.message.reply_text(help_text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user = user_collection.find_one({"user_id": user_id})
    if user:
        profile_info = (
            f"◉ 👤 **Profile** 👤 ◉\n"
            f"⌲ Level: {user['level']} 🌟\n"
            f"⌲ Coins: {user['coins']} 💰\n"
            f"⌲ Guesses Left until Reset: {config.MESSAGE_THRESHOLD - user['guess_count']} 🔄"
        )
    else:
        profile_info = "❌ User profile not found."
    await update.message.reply_text(profile_info)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    leaderboard_text = game.get_leaderboard()
    await update.message.reply_text(leaderboard_text)

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.message.from_user.id
    try:
        new_sudo_id = int(context.args[0])
        response = game.add_sudo_user(new_sudo_id, current_user_id)
        await update.message.reply_text(response)
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addsudo <user_id>")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    guess_text = update.message.text
    correct, response, status = game.guess_character(user_id, guess_text)

    if correct:
        user_info = game.get_or_create_user(user_id)
        await update.message.reply_text(f"🎉 Correct! 🎉 You've earned {response} coins. Total coins: {user_info['coins']} 💰. Level: {user_info['level']} 🌟")

        if status == "threshold_reached":
            await update.message.reply_text("🔄 You've reached the threshold! Here’s a new character to keep the game going.")
        
        # Send the next character automatically with rarity caption
        game.start_game()
        rarity_emoji = game.selected_character.get("emoji", "")
        await update.message.reply_text(f"◉ {rarity_emoji} **A new character has appeared! Start guessing!** {rarity_emoji} ◉")
    else:
        await update.message.reply_text(f"❌ Incorrect! Hint: {response}")

async def send_character_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.start_game()
    rarity_emoji = game.selected_character.get("emoji", "")
    await update.message.reply_text(f"◉ {rarity_emoji} **A new character has appeared! Start guessing!** {rarity_emoji} ◉")


# Setting up the bot and command handlers with infinite polling
def main():
    application = Application.builder().token(config.API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("addsudo", add_sudo, filters.User(config.BOT_OWNER_ID)))
    application.add_handler(CommandHandler("upload", upload, filters.User(config.BOT_OWNER_ID) | filters.UserFilter(lambda user_id: user_id in game.sudo_users)))

    # Allows users to guess without using /guess by listening for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess))

    # Infinite polling to keep the bot running
    application.run_polling(allowed_updates=Update.ALL)


if __name__ == "__main__":
    main()
                
