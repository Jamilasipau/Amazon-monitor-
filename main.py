import telebot
import requests
from bs4 import BeautifulSoup
import time
import schedule
import re
from pymongo import MongoClient

# Replace with your bot token
BOT_TOKEN = "7568844140:AAHLvHjyMNvhSAfpk3m7RYRjPflxeSeK8uo"
bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB setup
MONGO_CONNECTION_STRING = "mongodb+srv://botplays:botplays@vulpix.ffdea.mongodb.net/?retryWrites=true&w=majority&appName=Vulpix"
client = MongoClient(MONGO_CONNECTION_STRING)
db = client["amazon_price_bot"]
products_collection = db["monitored_products"]

# Function to fetch product title and price from Amazon
def fetch_price(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return "Unknown Product", None

        soup = BeautifulSoup(response.content, "html.parser")
        
        # Fetch product title
        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Product"

        # Fetch product price
        price_whole = soup.find("span", {"class": "a-price-whole"})
        price_fraction = soup.find("span", {"class": "a-price-fraction"})
        if price_whole and price_fraction:
            price = float(
                price_whole.get_text(strip=True).replace(",", "")
                + "."
                + price_fraction.get_text(strip=True)
            )
        else:
            price = None

        return title, price
    except Exception as e:
        print(f"Error fetching price: {e}")
        return "Unknown Product", None

# Command: /start
@bot.message_handler(commands=["start"])
def start_command(message):
    bot.reply_to(
        message,
        "Welcome to the Amazon Price Tracker Bot By @botplays90!\n\n"
        "Use /help To For Usage"
    )

# Command: /help
@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "Here Are The Available Commands:\n"
        "/monitor <Amazon URL> - Start Monitoring A Product\n"
        "/history <Amazon URL> - View Price History Of A Product\n"
        "/stop <Amazon URL> - Stop Monitoring A Product\n"
        "/list - Shows The List Of Monitored Products\n"
        "/help - View Available Commands"
    )

# Command: /monitor
@bot.message_handler(commands=["monitor"])
def start_monitoring(message):
    try:
        url = message.text.split(" ", 1)[1].strip()
        
        if not re.match(r"https?://(www\.)?amazon\.[a-z]{2,3}/", url):
            bot.reply_to(message, "Please send a valid Amazon product link.")
            return

        user_id = message.chat.id
        existing_product = products_collection.find_one({"user_id": user_id, "url": url})
        if existing_product:
            bot.reply_to(message, "This product is already being monitored.")
            return

        title, current_price = fetch_price(url)
        if current_price is None:
            bot.reply_to(message, "Failed to fetch the product details. Please try again.")
            return

        products_collection.insert_one({
            "user_id": user_id,
            "url": url,
            "title": title,
            "last_price": current_price,
            "highest_price": current_price,
            "lowest_price": current_price,
        })

        bot.reply_to(
            message,
            f"Started monitoring:\n\nProduct: {title}\nCurrent Price: ₹{current_price}\n\nLink: {url}",
        )
    except IndexError:
        bot.reply_to(message, "Please provide an Amazon product link after /monitor.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")
        
# Command: /list
@bot.message_handler(commands=["list"])
def list_products(message):
    user_id = message.chat.id
    products = list(products_collection.find({"user_id": user_id}))

    if not products:
        bot.reply_to(message, "You are not monitoring any products currently.")
    else:
        reply = "Your Monitored Products:\n\n"
        for product in products:
            title = product.get("title", "Unknown Product")
            url = product.get("url", "No URL available")
            last_price = product.get("last_price", "N/A")
            highest_price = product.get("highest_price", "N/A")
            lowest_price = product.get("lowest_price", "N/A")

            reply += (
                f"Product: {title}\n"
                f"Last Price: ₹{last_price}\n"
                f"Highest Price: ₹{highest_price}\n"
                f"Lowest Price: ₹{lowest_price}\n"
                f"Link: {url}\n\n"
            )
        bot.reply_to(message, reply)
                
# Command: /history
@bot.message_handler(commands=["history"])
def product_history(message):
    try:
        url = message.text.split(" ", 1)[1].strip()
        user_id = message.chat.id

        product = products_collection.find_one({"user_id": user_id, "url": url})
        if product:
            title = product.get("title", "Unknown Product")
            highest_price = product.get("highest_price", "Unknown")
            lowest_price = product.get("lowest_price", "Unknown")
            last_price = product.get("last_price", "Unknown")

            bot.reply_to(
                message,
                f"Price History for:\n{title}\n\n"
                f"Highest Price: ₹{highest_price}\n"
                f"Lowest Price: ₹{lowest_price}\n"
                f"Last Recorded Price: ₹{last_price}\n\n"
                f"Product Link: {url}"
            )
        else:
            bot.reply_to(message, "This product is not being monitored.")
    except IndexError:
        bot.reply_to(message, "Please provide the Amazon product link after /history.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# Command: /stop
@bot.message_handler(commands=["stop"])
def stop_monitoring(message):
    try:
        url = message.text.split(" ", 1)[1].strip()
        user_id = message.chat.id

        result = products_collection.delete_one({"user_id": user_id, "url": url})
        if result.deleted_count > 0:
            bot.reply_to(message, "Stopped monitoring the product.")
        else:
            bot.reply_to(message, "This product is not being monitored.")
    except IndexError:
        bot.reply_to(message, "Please provide the Amazon product link after /stop.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# Function to check prices and send updates
def check_prices():
    for product in products_collection.find():
        user_id = product["user_id"]
        url = product["url"]
        last_price = product["last_price"]
        highest_price = product["highest_price"]
        lowest_price = product["lowest_price"]

        try:
            title, current_price = fetch_price(url)
            if current_price is not None:
                updated = False
                if current_price > highest_price:
                    highest_price = current_price
                    updated = True
                if current_price < lowest_price:
                    lowest_price = current_price
                    updated = True

                if current_price != last_price or updated:
                    message = (
                        f"Price Update for {title}:\n\n"
                        f"Current Price: ₹{current_price}\n"
                        f"Highest Price: ₹{highest_price}\n"
                        f"Lowest Price: ₹{lowest_price}\n\n"
                        f"Product Link: {url}"
                    )
                    bot.send_message(user_id, message)

                products_collection.update_one(
                    {"_id": product["_id"]},
                    {"$set": {"last_price": current_price, "highest_price": highest_price, "lowest_price": lowest_price}},
                )
        except Exception as e:
            bot.send_message(user_id, f"Error monitoring product: {e}")

# Schedule the price check every 5 minutes
schedule.every(5).minutes.do(check_prices)

# Background job to run the schedule
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

import threading
threading.Thread(target=run_schedule, daemon=True).start()

# Start the bot
while True:
    try:
        bot.polling()
    except Exception as e:
        print(f"Bot polling error: {e}")
        time.sleep(5)
        
