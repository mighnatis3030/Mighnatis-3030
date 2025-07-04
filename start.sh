#!/bin/bash

# Ensure the config.json and users.json files exist
# This helps in case of initial deployment or disk issues
touch config.json
touch users.json

# Start the bot
python wheel_bot.py
