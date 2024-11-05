from datetime import timedelta

# Bot API token (replace with your actual token)
API_TOKEN = "6862816736:AAGwMwi3twYHX_BiQhPAWI67_a4pCUfMLRc"

# MongoDB connection URI
MONGO_URI = "mongodb+srv://PhiloWise:Philo@waifu.yl9tohm.mongodb.net/?retryWrites=true&w=majority&appName=Waifu"

# Bot Owner and Channel IDs
BOT_OWNER_ID = 7222795580  # Owner's Telegram ID
CHARACTER_CHANNEL_ID = -1002438449944  # Channel ID for posting and retrieving characters

# Game Settings
BONUS_COINS = 50000               # Daily bonus coins for /bonus command
STREAK_BONUS_COINS = 1000         # Additional coins for maintaining a streak
BONUS_INTERVAL = timedelta(days=1)  # Time interval for claiming daily bonus

COINS_PER_GUESS = 50              # Coins awarded for a correct guess
MESSAGE_THRESHOLD = 5             # Messages needed in group to trigger character appearance
TOP_LEADERBOARD_LIMIT = 10        # Limit for the top leaderboard display

# Character Rarity Settings
RARITY_LEVELS = {
    'Bronze': '🥉',
    'Silver': '🥈',
    'Gold': '🥇',
    'Platinum': '🏆',
    'Diamond': '💎'
}
RARITY_WEIGHTS = [40, 30, 15, 10, 5]  # Probability distribution for each rarity level
