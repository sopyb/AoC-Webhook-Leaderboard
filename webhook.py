import requests
import json
from datetime import datetime
import os
import time
import signal
import sys
import logging
from dotenv import load_dotenv


class AoCDiscordBot:
    def __init__(self):
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('bot.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Flag for graceful shutdown
        self.running = True

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Load environment variables
        load_dotenv()

        # Required environment variables
        self.session_cookie = os.getenv('AOC_SESSION_COOKIE')
        self.leaderboard_id = os.getenv('AOC_LEADERBOARD_ID')
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')

        # Optional configuration
        self.base_url = os.getenv('AOC_BASE_URL', 'https://adventofcode.com')
        self.message_store_file = os.getenv('MESSAGE_STORE_FILE',
                                            'discord_messages.json')

        # Validate required environment variables
        self._validate_config()

        # Extract webhook ID and token from URL
        webhook_parts = self.discord_webhook_url.split('/')
        self.webhook_id = webhook_parts[-2]
        self.webhook_token = webhook_parts[-1]

        # Load stored messages
        self.stored_messages = self.load_stored_messages()

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info("Received shutdown signal. Cleaning up...")
        self.running = False

    def _validate_config(self):
        """Validate that all required environment variables are set"""
        missing_vars = []
        if not self.session_cookie:
            missing_vars.append('AOC_SESSION_COOKIE')
        if not self.leaderboard_id:
            missing_vars.append('AOC_LEADERBOARD_ID')
        if not self.discord_webhook_url:
            missing_vars.append('DISCORD_WEBHOOK_URL')

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                "Please check your .env file"
            )

    def load_stored_messages(self):
        """Load stored message IDs from file"""
        if os.path.exists(self.message_store_file):
            try:
                with open(self.message_store_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_message_id(self, year, message_ids):
        """Save message IDs for a specific year"""
        self.stored_messages[str(year)] = message_ids
        with open(self.message_store_file, 'w') as f:
            json.dump(self.stored_messages, f)

    def fetch_leaderboard(self, year):
        """Fetch private leaderboard data from Advent of Code"""
        url = f"{self.base_url}/{year}/leaderboard/private/view/{self.leaderboard_id}.json"
        headers = {"Cookie": f"session={self.session_cookie}"}

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(
                f"Failed to fetch leaderboard: {response.status_code}")

    def format_leaderboard_message(self, data, year):
        """Format leaderboard data into multiple Discord messages with up to 20 players each"""
        members = data['members']
        members_with_stars = [m for m in members.values() if m['stars'] > 0]
        members_without_stars = [m for m in members.values() if m['stars'] == 0]

        sorted_members_with_stars = sorted(
            members_with_stars,
            key=lambda x: (-x['local_score'], -x['stars'])
        )
        sorted_members_without_stars = sorted(
            members_without_stars,
            key=lambda x: x.get('name', f"Anonymous User #{x['id']}") or ""
        )

        sorted_members = sorted_members_with_stars + sorted_members_without_stars

        all_embeds = []
        for i in range(0, min(len(sorted_members), 200), 5):
            chunk = sorted_members[i:i + 5]
            fields = []
            for rank, member in enumerate(chunk, start=i + 1):
                name = member.get('name',
                                  f"Anonymous User #{member['id']}") or f"(Anonymous User #{member['id']})"
                field_name = f"{rank}. {member['local_score']} - {name}"

                # Generate stars for each day
                stars_per_day = []
                for day in range(1, 26):
                    day_key = str(day)
                    if day_key in member['completion_day_level']:
                        stars = member['completion_day_level'][day_key]
                        if '2' in stars:
                            stars_per_day.append("<:star2:1310014071579611231>")
                        else:
                            stars_per_day.append("<:star1:1310014070019330188>")
                    else:
                        stars_per_day.append("<:star0:1310014068022575144>")

                    field_value = "".join(stars_per_day)

                # Generate stars for each day
                # star0_count = 0
                # star1_count = 0
                # star2_count = 0
                #
                # for day in range(1, 26):
                #     day_key = str(day)
                #     if day_key in member['completion_day_level']:
                #         stars = member['completion_day_level'][day_key]
                #         if '2' in stars:
                #             star2_count += 1
                #         else:
                #             star1_count += 1
                #     elif (
                #             datetime.now().month == 12 and day < datetime.now().day and datetime.now().year == year) or datetime.now().year > year:
                #         star0_count += 1
                #
                # field_value = f"<:star0:1310014068022575144> {star0_count}, <:star1:1310014070019330188> {star1_count}, <:star2:1310014071579611231> {star2_count}"

                fields.append({
                    "name": field_name,
                    "value": field_value,
                    "inline": False
                })

            if fields:  # Ensure fields is not empty
                embed = {
                    "title": f"🎄 Advent of Code Leaderboard 🎄 (Top {i + 1}-{i + len(chunk)})",
                    "fields": fields,
                    "timestamp": datetime.utcnow().isoformat(),
                    "color": 0x00ff00
                }
                all_embeds.append(embed)

        messages = []
        current_message = []
        current_size = 0

        for embed in all_embeds:
            embed_size = len(json.dumps(embed))
            if current_size + embed_size > 6000:
                if current_message:  # Ensure current_message is not empty
                    messages.append(current_message)
                current_message = [embed]
                current_size = embed_size
            else:
                current_message.append(embed)
                current_size += embed_size

        if current_message:  # Ensure current_message is not empty
            messages.append(current_message)

        return messages

    def edit_discord_message(self, message_ids, embeds):
        """Edit existing Discord messages"""
        for message_id, embed in zip(message_ids, embeds):
            url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}/messages/{message_id}"
            payload = {
                "embeds": embed,
                "username": "AoC Leaderboard Bot",
                "avatar_url": "https://adventofcode.com/favicon.png"
            }

            response = requests.patch(url, json=payload)
            if response.status_code != 200:
                self.logger.error(
                    f"Failed to edit Discord message: {response.status_code}, {response.text}")
                self.logger.info(f"Payload: {json.dumps(payload, indent=2)}")
                raise Exception(
                    f"Failed to edit Discord message: {response.status_code}")

    def delete_discord_message(self, message_id):
        """Delete a Discord message"""
        url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}/messages/{message_id}"
        response = requests.delete(url)
        if response.status_code == 404:
            self.logger.warning(
                f"Discord message {message_id} not found (404). It may have been deleted already.")
        elif response.status_code != 204:
            raise Exception(
                f"Failed to delete Discord message: {response.status_code}")

    def send_to_discord(self, embeds):
        """Send formatted embeds to Discord webhook"""
        message_ids = []
        for embed in embeds:
            payload = {
                "embeds": embed,
                "username": "AoC Leaderboard Bot",
                "avatar_url": "https://adventofcode.com/favicon.png"
            }

            response = requests.post(f"{self.discord_webhook_url}?wait=true",
                                     json=payload)
            if response.status_code == 200:
                message_ids.append(response.json().get('id'))
            else:
                raise Exception(
                    f"Failed to send Discord message: {response.status_code}")
        return message_ids

    def update_leaderboard(self, year):
        """Fetch leaderboard and send/update Discord messages"""
        try:
            data = self.fetch_leaderboard(year)
            messages = self.format_leaderboard_message(data, year)

            year_key = str(year)
            existing_message_ids = self.stored_messages.get(year_key, [])

            # Create new messages if we have more than stored
            if len(messages) > len(existing_message_ids):
                new_messages = messages[len(existing_message_ids):]
                new_message_ids = self.send_to_discord(new_messages)
                existing_message_ids.extend(new_message_ids)

            # Update existing messages
            self.edit_discord_message(existing_message_ids[:len(messages)], messages)

            # Delete any extra messages
            for message_id in existing_message_ids[len(messages):]:
                self.delete_discord_message(message_id)

            # Update stored message IDs
            self.stored_messages[year_key] = existing_message_ids[:len(messages)]
            self.save_message_id(year, self.stored_messages[year_key])

        except Exception as e:
            self.logger.error(f"Error updating leaderboard: {str(e)}")

    def run_forever(self):
        """Run the bot forever, updating at specified intervals"""
        update_interval = int(os.getenv('UPDATE_INTERVAL', 900))
        self.logger.info(
            f"Starting bot with {update_interval} seconds update interval")

        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Check if it's time for an update
            if current_time - last_update_time >= update_interval:
                try:
                    self.logger.info("Updating leaderboard...")
                    self.update_leaderboard(
                        int(os.getenv('AOC_LEADERBOARD_YEAR', 2024)))
                    last_update_time = current_time
                    self.logger.info("Update successful")
                except Exception as e:
                    self.logger.error(f"Update failed: {str(e)}")
                    # If there's an error, wait a bit before retrying
                    time.sleep(60)
                    continue

            # Sleep for a short interval to prevent CPU spinning
            # Calculate time until next update
            time_until_next = update_interval - (time.time() - last_update_time)
            # Sleep in shorter intervals to allow for clean shutdown
            time.sleep(min(60, max(1, time_until_next)))

        self.logger.info("Bot shutdown complete")


if __name__ == "__main__":
    try:
        bot = AoCDiscordBot()
        bot.run_forever()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        sys.exit(1)
