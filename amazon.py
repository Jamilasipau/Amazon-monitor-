import telebot
import requests
from bs4 import BeautifulSoup
import time
import schedule
import re
from pymongo import MongoClient

# Replace with your bot token
BOT_TOKEN = "7691950524:AAEwx9DGbn-HKRLJjJuqGAdVtRPbaNUTrx8"
bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB setup
MONGO_CONNECTION_STRING = "mongodb+srv://botplays:botplays@vulpix.ffdea.mongodb.net/?retryWrites=true&w=majority&appName=Vulpix"  # Replace with your MongoDB URI
client = MongoClient(MONGO_CONNECTION_STRING)
db = client["amazon_price_bot"]
products_collection = db["monitored_products"]

# Function to scrape Amazon product price
def fetch_price(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # Scrape product title
    title = soup.find("span", {"id": "productTitle"})
    if title:
        title = title.get_text(strip=True)
    else:
        title = "Unknown Product"

    # Scrape price
    price_tag = soup.find("span", {"class": "a-price-whole"})
    if price_tag:
        price = float(price_tag.get_text(strip=True).replace(",", "").replace(".", ""))
    else:
        price = None

    return title, price

# Function to check prices and send updates
def check_prices():
    for product in products_collection.find():
        user_id = product["user_id"]
        url = product["url"]
        last_price = product["last_price"]

        try:
            title, current_price = fetch_price(url)
            if current_price is not None and (last_price is None or current_price != last_price):
                if last_price is not None:
                    drop = last_price - current_price
                    message = (
                        f"Price Alert!\n\n"
                        f"Product: {title}\n"
                        f"Current Price: ₹{current_price}\n"
                        f"Price Dropped by: ₹{drop:.2f}\n\n"
                        f"Link: {url}"
                    )
                else:
                    message = (
                        f"Monitoring Started!\n\n"
                        f"Product: {title}\n"
                        f"Current Price: ₹{current_price}\n\n"
                        f"Link: {url}"
                    )
                bot.send_message(user_id, message)
                # Update the price in the database
                products_collection.update_one({"_id": product["_id"]}, {"$set": {"last_price": current_price}})
        except Exception as e:
            bot.send_message(user_id, f"Error monitoring product: {e}")

# Command to start monitoring a product
@bot.message_handler(commands=["monitor"])
def start_monitoring(message):
    try:
        url = message.text.split(" ", 1)[1]
        # Validate if the link is an Amazon link
        if not re.match(r"https?://(www\.)?amazon\.[a-z]{2,3}/", url):
            bot.reply_to(message, "Please send a valid Amazon product link.")
            return

        user_id = message.chat.id
        # Check if the product is already monitored by this user
        existing_product = products_collection.find_one({"user_id": user_id, "url": url})
        if existing_product:
            bot.reply_to(message, "This product is already being monitored.")
            return

        title, current_price = fetch_price(url)
        products_collection.insert_one({"user_id": user_id, "url": url, "last_price": current_price})
        bot.reply_to(
            message,
            f"Started monitoring:\n\nProduct: {title}\nCurrent Price: ₹{current_price}\n\nLink: {url}",
        )
    except IndexError:
        bot.reply_to(message, "Please provide an Amazon product link after /monitor.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# Command to list all monitored products
@bot.message_handler(commands=["list"])
def list_products(message):
    user_id = message.chat.id
    products = products_collection.find({"user_id": user_id})
    if products_collection.count_documents({"user_id": user_id}) == 0:
        bot.reply_to(message, "No products are currently being monitored.")
    else:
        reply = "Monitored Products:\n"
        for product in products:
            reply += f"- {product['url']} (Last Price: ₹{product['last_price']})\n"
        bot.reply_to(message, reply)

# Command to stop monitoring a product
@bot.message_handler(commands=["stop"])
def stop_monitoring(message):
    try:
        url = message.text.split(" ", 1)[1]
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

# Schedule the price check every 24 hours
schedule.every(1).hours.do(check_prices)

# Background job to run the schedule
def run_schedule():
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"Error in scheduler: {e}")

import threading
threading.Thread(target=run_schedule, daemon=True).start()

# Start the bot
while True:
    try:
        bot.polling()
    except Exception as e:
        print(f"Bot polling error: {e}")
        time.sleep(5)
        