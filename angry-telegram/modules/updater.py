#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2019 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import os
import sys
import atexit
import functools
import random
import subprocess
import asyncio
import uuid

import git
from git import Repo

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class UpdaterMod(loader.Module):
    """Updates itself"""
    strings = {"name": "Updater",
               "source": "<b>Read the source code from</b> <a href='{}'>here</a>",
               "restarting_caption": "<b>Restarting...</b>",
               "downloading": "<b>Downloading updates...</b>",
               "downloaded": ("<b>Downloaded successfully.\nPlease type</b> "
                              "<code>.restart</code> <b>to restart the bot.</b>"),
               "already_updated": "<b>Already up to date!</b>",
               "installing": "<b>Installing updates...</b>",
               "success": "<b>Restart successful!</b>",
               "success_meme": "<b>Restart failed successfully‽</b>",
               "heroku_warning": ("Heroku API key has not been set. Update was successful but updates will "
                                  "reset every time the bot restarts."),
               "origin_cfg_doc": "Git origin URL, for where to update from"}

    def __init__(self):
        self.config = loader.ModuleConfig("GIT_ORIGIN_URL",
                                          "https://github.com/neongang/angry-telegram",
                                          lambda m: self.strings("origin_cfg_doc", m))

    @loader.owner
    async def restartcmd(self, message):
        """Restarts the userbot"""
        msg = (await utils.answer(message, self.strings("restarting_caption", message)))[0]
        await self.restart_common(msg)

    async def prerestart_common(self, message):
        logger.debug("Self-update. " + sys.executable + " -m " + utils.get_base_dir())
        check = str(uuid.uuid4())
        await self._db.set(__name__, "selfupdatecheck", check)
        await asyncio.sleep(3)
        if self._db.get(__name__, "selfupdatecheck", "") != check:
            raise ValueError("An update is already in progress!")
        self._db.set(__name__, "selfupdatechat", utils.get_chat_id(message))
        await self._db.set(__name__, "selfupdatemsg", message.id)

    async def restart_common(self, message):
        await self.prerestart_common(message)
        atexit.register(functools.partial(restart, *sys.argv[1:]))
        [handler] = logging.getLogger().handlers
        handler.setLevel(logging.CRITICAL)
        for client in self.allclients:
            # Terminate main loop of all running clients
            # Won't work if not all clients are ready
            if client is not message.client:
                await client.disconnect()
        await message.client.disconnect()

    @loader.owner
    async def downloadcmd(self, message):
        """Downloads userbot updates"""
        message = await utils.answer(message, self.strings("downloading", message))
        await self.download_common()
        await utils.answer(message, self.strings("downloaded", message))

    async def download_common(self):
        try:
            repo = Repo(os.path.dirname(utils.get_base_dir()))
            origin = repo.remote("origin")
            r = origin.pull()
            new_commit = repo.head.commit
            for info in r:
                if info.old_commit:
                    for d in new_commit.diff(info.old_commit):
                        if d.b_path == "requirements.txt":
                            return True
            return False
        except git.exc.InvalidGitRepositoryError:
            repo = Repo.init(os.path.dirname(utils.get_base_dir()))
            origin = repo.create_remote("origin", self.config["GIT_ORIGIN_URL"])
            origin.fetch()
            repo.create_head("master", origin.refs.master)
            repo.heads.master.set_tracking_branch(origin.refs.master)
            repo.heads.master.checkout(True)
            return False  # Heroku never needs to install dependencies because we redeploy

    def req_common(self):
        # Now we have downloaded new code, install requirements
        logger.debug("Installing new requirements...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                            os.path.join(os.path.dirname(utils.get_base_dir()), "requirements.txt"), "--user"])
        except subprocess.CalledProcessError:
            logger.exception("Req install failed")

    @loader.owner
    async def updatecmd(self, message):
        """Downloads userbot updates"""
        # We don't really care about asyncio at this point, as we are shutting down
        req_update = await self.download_common()
        message = (await utils.answer(message, self.strings("installing", message)))[0]
        heroku_key = os.environ.get("heroku_api_token")
        if heroku_key:
            from .. import heroku
            await self.prerestart_common(message)
            heroku.publish(self.allclients, heroku_key)
            # If we pushed, this won't return. If the push failed, we will get thrown at.
            # So this only happens when remote is already up to date (remote is heroku, where we are running)
            self._db.set(__name__, "selfupdatechat", None)
            self._db.set(__name__, "selfupdatemsg", None)
            await utils.answer(message, self.strings("already_updated", message))
        else:
            if req_update:
                self.req_common()
            await self.restart_common(message)

    @loader.unrestricted
    async def sourcecmd(self, message):
        """Links the source code of this project"""
        await utils.answer(message, self.strings("source", message).format(self.config["GIT_ORIGIN_URL"]))

    async def client_ready(self, client, db):
        self._db = db
        self._me = await client.get_me()
        if db.get(__name__, "selfupdatechat") is not None and db.get(__name__, "selfupdatemsg") is not None:
            await self.update_complete(client)
        self._db.set(__name__, "selfupdatechat", None)
        self._db.set(__name__, "selfupdatemsg", None)

    async def update_complete(self, client):
        logger.debug("Self update successful! Edit message")
        heroku_key = os.environ.get("heroku_api_token")
        herokufail = ("DYNO" in os.environ) and (heroku_key is None)
        if herokufail:
            logger.warning("heroku token not set")
            msg = self.strings("heroku_warning")
        else:
            logger.debug("Self update successful! Edit message")
            msg = self.strings("success") if random.randint(0, 10) != 0 else self.strings["success_meme"]
        await client.edit_message(self._db.get(__name__, "selfupdatechat"),
                                  self._db.get(__name__, "selfupdatemsg"), msg)


def restart(*argv):
    os.execl(sys.executable, sys.executable, "-m", os.path.relpath(utils.get_base_dir()), *argv)
