"""
Run this once (and again any time you change the command definitions below)
to register/update the slash commands with Discord.

Requires env vars:
  DISCORD_APPLICATION_ID
  DISCORD_BOT_TOKEN
"""
import os
import requests

APP_ID = os.environ["DISCORD_APPLICATION_ID"]
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
headers = {"Authorization": f"Bot {BOT_TOKEN}"}

STRING_TYPE = 3

commands = [
    {
        "name": "recommend",
        "description": "Get a listening recommendation",
        "options": [
            {
                "name": "prompt",
                "description": "Optional mood, composer, or vibe to steer the pick",
                "type": STRING_TYPE,
                "required": False,
            }
        ],
    },
    {
        "name": "add",
        "description": "Add a new piece to your listening list",
        "options": [
            {
                "name": "prompt",
                "description": "Describe the piece, e.g. \"Rachmaninoff's 2nd piano concerto\"",
                "type": STRING_TYPE,
                "required": True,
            }
        ],
    },
    {
        "name": "listened",
        "description": "Check off a piece as listened",
        "options": [
            {
                "name": "composer",
                "description": "Composer name",
                "type": STRING_TYPE,
                "required": True,
            },
            {
                "name": "title",
                "description": "Piece title",
                "type": STRING_TYPE,
                "required": True,
            },
        ],
    },
]

resp = requests.put(url, headers=headers, json=commands, timeout=10)
resp.raise_for_status()
print("Registered commands:", [c["name"] for c in resp.json()])
