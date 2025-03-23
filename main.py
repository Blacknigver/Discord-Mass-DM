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

os.system('cls' if os.name == 'nt' else 'clear')

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

CAPMONSTER_API_KEY = os.getenv("CAPMONSTER_API_KEY")

async def solve_hcaptcha(site_key, page_url, rqdata=None):
    if not CAPMONSTER_API_KEY:
        logging.error("CapMonster API key not found.")
        return None

    try:
        task_payload = {
            "clientKey": CAPMONSTER_API_KEY,
            "task": {
                "type": "HCaptchaTaskProxyless",
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
            create_data = await create_resp.json()
            if create_data.get("errorId") != 0:
                logging.error(f"createTask error: {create_data.get('errorDescription')}")
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
                result_data = await result_resp.json()

                if result_data.get("errorId") != 0:
                    logging.error(f"getTaskResult error: {result_data.get('errorDescription')}")
                    return None

                if result_data.get("status") == "ready":
                    return result_data.get("solution", {}).get("gRecaptchaResponse")
            logging.error("Captcha solve timeout.")
            return None

    except Exception as e:
        logging.error(f"Exception during captcha solving: {e}")
        return None

class Discord:
    def __init__(self):
        self.clear = (lambda: os.system("clear")) if sys.platform == "linux" else (lambda: os.system("cls"))
        self.clear()

        self.tokens = []
        for i in range(1, 11):
            token = os.getenv(f"TOKEN_{i}")
            if token:
                self.tokens.append(token)

        if not self.tokens:
            logging.info("No tokens found. Exiting.")
            sys.exit()

        self.invite = os.getenv("DISCORD_INVITE")
        self.message = os.getenv("DM_MESSAGE", "Hello!").replace("\\n", "\n")
        try:
            self.delay = float(os.getenv("DM_DELAY", "0"))
        except:
            self.delay = 0

        self.guild_name = None
        self.guild_id = None
        self.channel_id = None

    def stop(self):
        psutil.Process(os.getpid()).terminate()

    def nonce(self):
        ts = time.mktime(datetime.now().timetuple())
        return str((int(ts) * 1000 - 1420070400000) * 4194304)

    async def headers(self, token):
        async with ClientSession() as session:
            async with session.get("https://discord.com/app") as r:
                cookies = str(r.cookies)
                dcfduid = cookies.split("dcfduid=")[1].split(";")[0]
                sdcfduid = cookies.split("sdcfduid=")[1].split(";")[0]

        return {
            "Authorization": token,
            "accept": "*/*",
            "cookie": f"__dcfduid={dcfduid}; __sdcfduid={sdcfduid}; locale=en-US",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) discord/1.0.9001 Chrome/83.0.4103.122 "
                "Electron/9.3.5 Safari/537.36"
            )
        }

    async def login(self, token):
        try:
            h = await self.headers(token)
            async with ClientSession(headers=h) as c:
                async with c.get("https://discord.com/api/v9/users/@me/library") as r:
                    if r.status != 200:
                        self.tokens.remove(token)
        except:
            self.tokens.remove(token)

    async def join(self, token):
        try:
            h = await self.headers(token)
            url = f"https://discord.com/api/v9/invites/{self.invite}"
            async with ClientSession(headers=h) as c:
                async with c.post(url, json={}) as r:
                    data = await r.json()
                    if "captcha_sitekey" in data:
                        solution = await solve_hcaptcha(
                            data["captcha_sitekey"],
                            "https://discord.com",
                            data.get("captcha_rqdata")
                        )
                        if solution:
                            payload = {
                                "captcha_key": solution,
                                "captcha_rqtoken": data.get("captcha_rqtoken")
                            }
                            async with c.post(url, json=payload) as r2:
                                d = await r2.json()
                                if r2.status == 200:
                                    self.guild_name = d["guild"]["name"]
                                    self.guild_id = d["guild"]["id"]
                                    self.channel_id = d["channel"]["id"]
                                else:
                                    self.tokens.remove(token)
                        else:
                            self.tokens.remove(token)
                    elif r.status == 200:
                        self.guild_name = data["guild"]["name"]
                        self.guild_id = data["guild"]["id"]
                        self.channel_id = data["channel"]["id"]
                    else:
                        self.tokens.remove(token)
        except:
            self.tokens.remove(token)

    async def create_dm(self, token, user):
        try:
            h = await self.headers(token)
            async with ClientSession(headers=h) as c:
                async with c.post("https://discord.com/api/v9/users/@me/channels", json={"recipients": [user]}) as r:
                    if r.status == 200:
                        return (await r.json())["id"]
                    self.tokens.remove(token)
        except:
            self.tokens.remove(token)
        return False

    async def direct_message(self, token, channel):
        try:
            h = await self.headers(token)
            payload = {"content": self.message, "nonce": self.nonce(), "tts": False}
            async with ClientSession(headers=h) as c:
                async with c.post(f"https://discord.com/api/v9/channels/{channel}/messages", json=payload) as r:
                    d = await r.json()
                    if "captcha_sitekey" in d:
                        solution = await solve_hcaptcha(
                            d["captcha_sitekey"], "https://discord.com", d.get("captcha_rqdata")
                        )
                        if solution:
                            payload["captcha_key"] = solution
                            payload["captcha_rqtoken"] = d.get("captcha_rqtoken")
                            async with c.post(f"https://discord.com/api/v9/channels/{channel}/messages", json=payload) as r2:
                                return r2.status == 200
                        self.tokens.remove(token)
                        return False
                    return r.status == 200
        except:
            return False

    async def send(self, token, user):
        channel = await self.create_dm(token, user)
        if not channel:
            return
        await self.direct_message(token, channel)

    async def start(self):
        if not self.tokens:
            self.stop()

        async with TaskPool(1000) as pool:
            for token in self.tokens:
                await pool.put(self.login(token))

        async with TaskPool(1000) as pool:
            for token in self.tokens:
                await pool.put(self.join(token))
                if self.delay:
                    await asyncio.sleep(self.delay)

        scraper = Scraper(self.guild_id, self.channel_id, self.tokens[0])
        self.users = scraper.fetch()

        async with TaskPool(1000) as pool:
            for user in self.users:
                await pool.put(self.send(random.choice(self.tokens), user))
                if self.delay:
                    await asyncio.sleep(self.delay)

if __name__ == "__main__":
    clear_screen()
    client = Discord()
    asyncio.get_event_loop().run_until_complete(client.start())
