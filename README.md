# Telegram Trivia Bot Setup Guide

This guide will walk you through setting up your Trivia Bot on Replit.

## Step-by-Step Instructions

### 1. Create a Telegram Bot

* Open Telegram and search for a bot called **`@BotFather`**.
* Start a chat and send the command `/newbot`.
* Follow the instructions to give your bot a name and a username.
* BotFather will give you a long **API Token**. Copy this token.

### 2. Set Up Secrets in Replit

This is the most important step for security.

* In your Replit project, find the **"Secrets"** tab on the left (it looks like a padlock 🔒).
* Add three secrets:

    * **Key:** `TELEGRAM_BOT_TOKEN`
    * **Value:** Paste the token from BotFather.

    * **Key:** `CHAPA_SECRET_KEY`
    * **Value:** Paste your Chapa Secret Key. (Use a test key for now, e.g., `CHSK_TEST_...`).

    * **Key:** `ADMIN_TELEGRAM_ID`
    * **Value:** Find your personal Telegram ID by sending `/start` to the bot `@userinfobot`.

### 3. Run the Bot

* After pasting the code and setting your secrets, click the big green **"Run"** button at the top of Replit.
* The Replit console should show "Bot started..." which means it's working!

### 4. Keep the Bot Running 24/7

* A free Replit account stops your bot when you close the browser.
* When you run the bot, a URL will appear at the top of the preview window. It looks like `https://your-project.your-name.replit.dev`.
* Use a free service like **UptimeRobot**. Create an account, add a "New Monitor", select "HTTP(s)", and paste your Replit URL. This "pings" your bot every few minutes to keep it alive.

Your bot is now ready! Find it on Telegram and send `/start` to begin.
