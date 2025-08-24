# Intents toggles used by bot.py
INTENTS_KWARGS = dict(
    message_content=True,
    members=True,
)

# Reminder mentions
MENTION_EVERYONE = True          # set False to disable @everyone
MENTION_ROLE_ID = None           # set an int role id to ping that role instead
REMINDER_CHECKPOINTS = ["half", 4*3600, 15*60, 5*60]