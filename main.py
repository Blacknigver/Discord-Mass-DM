#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import random
import logging
import asyncio
import aiohttp
import psutil

from datetime import datetime
from tasksio import TaskPool
from lib.scraper import Scraper
from aiohttp import ClientSession

logging.basicConfig(
    level=logging.INFO,
    format="\x1b[38;5;9m[\x1b[0m%(asctime)s\x1b[38;5;9m]\x1b[0m %(message)s\x1b[0m",
    datefmt="%H:%M:%S"
)

# Clear screen (works on Windows and Linux; 'cls' is ignored on Linux)
os.system('cls' if os.name == 'nt' else 'clear')

def clear_screen() -> None:
    """
    Clears the terminal screen.
    """
    os.system('cls' if os.name == 'nt' else 'clear')

# ----------------------------------------------------
# CAPMONSTER HELPERS
# ----------------------------------------------------

CAPMONSTER_API_KEY = os.getenv("CAPMONSTER_API_KEY")

async def solve_hcaptcha(site_key: str, page_url: str, rqdata: str = None) -> str:
    """
    Solve an hCaptcha challenge using CapMonster.Cloud API.
    Returns the captcha solution token (captcha_key) or None if failed.
    """
    if not CAPMONSTER_API_KEY:
        logging.error("CapMonster API key not found in environment. Cannot solve captcha.")
        return None

    try:
        task_payload = {
            "clientKey": CAPMONSTER_API_KEY,
            "task": {
                # Changed task type to HCaptchaTask for compatibility.
                "type": "HCaptchaTask",
                "websiteURL": page_url,
                "websiteKey": site_key
            }
        }

        if rqdata:
            task_payload["task"]["enterprisePayload"] = {"rqdata": rqdata}
            task_payload["task"]["userAgent"] = (
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) discord/1.0.9001 Chrome/83.0.4103.122 "
                "Electron/9.3.5 Safari/537.36"
            )

        async with aiohttp.ClientSession() as session:
            create_resp = await session.post(
                "https://api.capmonster.cloud/createTask",
                json=task_payload,
                headers={"Content-Type": "application/json"}
            )
            # Force JSON decoding even if the response mimetype is not application/json.
            create_data = await create_resp.json(content_type=None)
            if create_data.get("errorId") != 0:
                logging.error(f"CapMonster createTask error: {create_data.get('errorDescription')}")
                return None

            task_id = create_data.get("taskId")
            logging.info(f"CapMonster task created: {task_id}")

            result_payload = {"clientKey": CAPMONSTER_API_KEY, "taskId": task_id}
            for _ in range(20):
                await asyncio.sleep(3)
                result_resp = await session.post(
                    "https://api.capmonster.cloud/getTaskResult",
                    json=result_payload,
                    headers={"Content-Type": "application/json"}
                )
                result_data = await result_resp.json(content_type=None)

                if result_data.get("errorId") != 0:
                    logging.error(f"CapMonster getTaskResult error: {result_data.get('errorDescription')}")
                    return None

                if result_data.get("status") == "ready":
                    solution = result_data.get("solution", {}).get("gRecaptchaResponse")
                    if solution:
                        logging.info("Captcha solved via CapMonster")
                        return solution
                    else:
                        logging.error("CapMonster returned no solution")
                        return None

            logging.error("CapMonster solve timed out (no solution after ~60s)")
            return None

    except Exception as e:
        logging.error(f"Exception during captcha solving: {e}")
        return None

# ----------------------------------------------------
# DISCORD BOT CLASS
# ----------------------------------------------------

class Discord:
    """
    A class to handle Discord token login, server join, and mass DM operations.
    """

    def __init__(self) -> None:
        # Cross-platform clear function
        self.clear = (lambda: os.system("clear")) if sys.platform == "linux" else (lambda: os.system("cls"))
        self.clear()

        self.tokens: list[str] = []
        self.guild_name: str | None = None
        self.guild_id: str | None = None
        self.channel_id: str | None = None

        # --- LOAD TOKENS FROM ENVIRONMENT VARIABLES ---
        for i in range(1, 11):  # TOKEN_1 through TOKEN_10
            token = os.getenv(f"TOKEN_{i}")
            if token:
                self.tokens.append(token)

        if not self.tokens:
            logging.info("No tokens found in environment variables (TOKEN_1, TOKEN_2, ...). Exiting.")
            sys.exit()

        logging.info(f"Successfully loaded \x1b[38;5;9m{len(self.tokens)}\x1b[0m token(s)\n")

        # --- GET INVITE, MESSAGE, AND DELAY FROM ENV VARS ---
        self.invite = os.getenv("DISCORD_INVITE")  # e.g. "abc123" from "discord.gg/abc123"
        self.message = os.getenv("DM_MESSAGE", "Hello!").replace("\\n", "\n")
        try:
            self.delay = float(os.getenv("DM_DELAY", "0"))
        except Exception:
            self.delay = 0

        print()

    def stop(self) -> None:
        """
        Terminates the current process.
        """
        process = psutil.Process(os.getpid())
        process.terminate()

    def nonce(self) -> str:
        """
        Generates a nonce value based on the current time.
        """
        date = datetime.now()
        unixts = time.mktime(date.timetuple())
        return str((int(unixts) * 1000 - 1420070400000) * 4194304)

    async def headers(self, token: str) -> dict:
        """
        Generates HTTP headers for Discord requests using cookies.
        """
        async with ClientSession() as session:
            async with session.get("https://discord.com/app") as response:
                cookies = str(response.cookies)
                dcfduid = cookies.split("dcfduid=")[1].split(";")[0]
                sdcfduid = cookies.split("sdcfduid=")[1].split(";")[0]

        return {
            "Authorization": token,
            "accept": "*/*",
            "accept-language": "en-US",
            "connection": "keep-alive",
            "cookie": f"__dcfduid={dcfduid}; __sdcfduid={sdcfduid}; locale=en-US",
            "DNT": "1",
            "origin": "https://discord.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "referer": "https://discord.com/channels/@me",
            "TE": "Trailers",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) discord/1.0.9001 Chrome/83.0.4103.122 "
                "Electron/9.3.5 Safari/537.36"
            )
        }

    async def login(self, token: str) -> None:
        """
        Attempts to log in with the given token.
        """
        try:
            headers = await self.headers(token)
            async with ClientSession(headers=headers) as client:
                async with client.get("https://discord.com/api/v9/users/@me/library") as response:
                    if response.status == 200:
                        logging.info(f"Successfully logged in \x1b[38;5;9m({token[:59]})\x1b[0m")
                    elif response.status == 401:
                        logging.info(f"Invalid account \x1b[38;5;9m({token[:59]})\x1b[0m")
                        self.tokens.remove(token)
                    elif response.status == 403:
                        logging.info(f"Locked account \x1b[38;5;9m({token[:59]})\x1b[0m")
                        self.tokens.remove(token)
                    elif response.status == 429:
                        logging.info(f"Ratelimited \x1b[38;5;9m({token[:59]})\x1b[0m")
                        await asyncio.sleep(self.delay)
                        await self.login(token)
        except Exception:
            await self.login(token)

    async def join(self, token: str) -> None:
        """
        Attempts to join a Discord server using an invite code.
        """
        try:
            headers = await self.headers(token)
            url = f"https://discord.com/api/v9/invites/{self.invite}"
            async with ClientSession(headers=headers) as client:
                async with client.post(url, json={}) as response:
                    resp_json = await response.json()

                    # If a captcha is required to join
                    if "captcha_sitekey" in resp_json:
                        logging.info(f"Captcha required for joining server, solving via CapMonster... ({token[:20]}...)")
                        sitekey = resp_json.get("captcha_sitekey")
                        rqtoken = resp_json.get("captcha_rqtoken")
                        rqdata = resp_json.get("captcha_rqdata")

                        captcha_solution = await solve_hcaptcha(sitekey, "https://discord.com", rqdata)
                        if captcha_solution:
                            # Retry the join with the solved captcha token
                            payload = {"captcha_key": captcha_solution, "captcha_rqtoken": rqtoken}
                            async with client.post(url, json=payload) as resp2:
                                resp2_json = await resp2.json()
                                if resp2.status == 200:
                                    # Joined successfully after captcha solve
                                    self.guild_name = resp2_json["guild"]["name"]
                                    self.guild_id = resp2_json["guild"]["id"]
                                    self.channel_id = resp2_json["channel"]["id"]
                                    logging.info(
                                        f"Successfully joined {self.guild_name[:20]} "
                                        f"(Token {token[:59]}) [Captcha solved]"
                                    )
                                else:
                                    logging.error(
                                        f"Failed to join after captcha solve (status {resp2.status}): {resp2_json}"
                                    )
                                    self.tokens.remove(token)
                        else:
                            logging.error(
                                f"Could not solve join captcha for token {token[:20]}..., skipping token"
                            )
                            self.tokens.remove(token)
                        return  # exit after handling captcha success/fail

                    # If no captcha prompt, proceed with normal checks
                    if response.status == 200:
                        self.guild_name = resp_json["guild"]["name"]
                        self.guild_id = resp_json["guild"]["id"]
                        self.channel_id = resp_json["channel"]["id"]
                        logging.info(f"Successfully joined {self.guild_name[:20]} ({token[:59]})")
                    elif response.status in (401, 403):
                        logging.info(f"Invalid/Locked account ({token[:59]})")
                        self.tokens.remove(token)
                    elif response.status == 429:
                        logging.info(f"Ratelimited ({token[:59]})")
                        await asyncio.sleep(self.delay)
                        self.tokens.remove(token)
                    else:
                        self.tokens.remove(token)
        except Exception:
            # Retry on generic error
            await self.join(token)

    async def create_dm(self, token: str, user: str) -> str | bool:
        """
        Creates a direct message channel with a user.
        """
        try:
            headers = await self.headers(token)
            async with ClientSession(headers=headers) as client:
                url = "https://discord.com/api/v9/users/@me/channels"
                async with client.post(url, json={"recipients": [user]}) as response:
                    resp_json = await response.json()
                    if response.status == 200:
                        logging.info(
                            f"Successfully created DM with {resp_json['recipients'][0]['username']} "
                            f"\x1b[38;5;9m({token[:59]})\x1b[0m"
                        )
                        return resp_json["id"]
                    elif response.status in (401, 403):
                        logging.info(f"Invalid account or cannot message user ({token[:59]})")
                        self.tokens.remove(token)
                        return False
                    elif response.status == 429:
                        logging.info(f"Ratelimited ({token[:59]})")
                        await asyncio.sleep(self.delay)
                        return await self.create_dm(token, user)
                    else:
                        return False
        except Exception:
            return await self.create_dm(token, user)

    async def direct_message(self, token: str, channel: str) -> bool:
        """
        Sends a direct message to a specified channel.
        Returns False if sending fails, or None on success.
        """
        try:
            headers = await self.headers(token)
            url = f"https://discord.com/api/v9/channels/{channel}/messages"
            payload = {"content": self.message, "nonce": self.nonce(), "tts": False}
            async with ClientSession(headers=headers) as client:
                async with client.post(url, json=payload) as response:
                    resp_json = await response.json()

                    # If a captcha is required for DM
                    if "captcha_sitekey" in resp_json:
                        logging.info(f"Captcha required for DM, solving via CapMonster... ({token[:20]}...)")
                        sitekey = resp_json.get("captcha_sitekey")
                        rqtoken = resp_json.get("captcha_rqtoken")
                        rqdata = resp_json.get("captcha_rqdata")

                        captcha_solution = await solve_hcaptcha(sitekey, "https://discord.com", rqdata)
                        if captcha_solution:
                            # Retry sending the message with captcha solution
                            payload["captcha_key"] = captcha_solution
                            payload["captcha_rqtoken"] = rqtoken
                            async with client.post(url, json=payload) as resp2:
                                resp2_json = await resp2.json()
                                if resp2.status == 200:
                                    logging.info(f"Successfully sent DM (Token {token[:59]}) [Captcha solved]")
                                    return
                                else:
                                    logging.error(
                                        f"Failed to send DM after captcha solve (status {resp2.status}): {resp2_json}"
                                    )
                                    self.tokens.remove(token)
                                    return False
                        else:
                            logging.error(
                                f"Could not solve DM captcha for token {token[:20]}..., skipping token"
                            )
                            self.tokens.remove(token)
                            return False

                    # No captcha -> normal checks
                    if response.status == 200:
                        logging.info(f"Successfully sent message ({token[:59]})")
                    elif response.status == 401:
                        logging.info(f"Invalid account ({token[:59]})")
                        self.tokens.remove(token)
                        return False
                    elif response.status == 403:
                        if resp_json.get("code") == 40003:
                            logging.info(f"Ratelimited ({token[:59]})")
                            await asyncio.sleep(self.delay)
                            return await self.direct_message(token, channel)
                        elif resp_json.get("code") == 50007:
                            logging.info(f"User has DMs disabled ({token[:59]})")
                        elif resp_json.get("code") == 40002:
                            logging.info(f"Locked account ({token[:59]})")
                            self.tokens.remove(token)
                            return False
                    elif response.status == 429:
                        logging.info(f"Ratelimited ({token[:59]})")
                        await asyncio.sleep(self.delay)
                        return await self.direct_message(token, channel)
                    else:
                        return False
        except Exception:
            return await self.direct_message(token, channel)

    async def send(self, token: str, user: str) -> None:
        """
        Sends a DM message to a user by creating a DM channel and sending the message.
        """
        channel = await self.create_dm(token, user)
        if channel is False:
            return await self.send(random.choice(self.tokens), user)
        response = await self.direct_message(token, channel)
        if response is False:
            return await self.send(random.choice(self.tokens), user)

    async def start(self) -> None:
        """
        Main entry point to process tokens, join server, scrape users, and send messages.
        """
        if not self.tokens:
            logging.info("No tokens loaded.")
            sys.exit()

        # Login with all tokens
        async with TaskPool(1_000) as pool:
            for token in self.tokens:
                if self.tokens:
                    await pool.put(self.login(token))
                else:
                    self.stop()

        if not self.tokens:
            self.stop()

        print()
        logging.info("Joining server.")
        print()

        # Join the server using all tokens
        async with TaskPool(1_000) as pool:
            for token in self.tokens:
                if self.tokens:
                    await pool.put(self.join(token))
                    if self.delay:
                        await asyncio.sleep(self.delay)
                else:
                    self.stop()

        if not self.tokens:
            self.stop()

        # Scrape users from the joined server
        scraper = Scraper(
            token=self.tokens[0],
            guild_id=self.guild_id,
            channel_id=self.channel_id
        )
        self.users = scraper.fetch()

        print()
        logging.info(f"Successfully scraped \x1b[38;5;9m{len(self.users)}\x1b[0m members")
        logging.info("Sending messages.")
        print()

        if not self.tokens:
            self.stop()

        # Send messages to all scraped users
        async with TaskPool(1_000) as pool:
            for user in self.users:
                if self.tokens:
                    await pool.put(self.send(random.choice(self.tokens), user))
                    if self.delay:
                        await asyncio.sleep(self.delay)
                else:
                    self.stop()

if __name__ == "__main__":
    # =====================
    # Remove or comment out the lines below – they call start.bat and cause issues on Linux:
    #
    # if not os.getenv('requirements'):
    #     subprocess.Popen(['start', 'start.bat'], shell=True)
    #     sys.exit()
    #
    # =====================

    clear_screen()
    client = Discord()
    asyncio.get_event_loop().run_until_complete(client.start())