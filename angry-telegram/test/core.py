import asyncio
import os

from .. import security, utils, loader, main


user_modules = None


class TestManager:
    restart = asyncio.Future()

    def __init__(self, client, db, allclients, start_stage):
        self._client = client
        self._db = db
        self._clients = allclients
        self._start_stage = start_stage

    async def init(self):
        stage = self._db.get(__name__, "stage", None)
        if stage is None:
            stage = self._start_stage - 1
            await self._db.set(__name__, "stage", stage)
        if stage > 4:
            stage = 0
            await self._db.set(__name__, "stage", stage)
        if await self._client.is_bot():
            user_id = [(await c.get_me(True)).user_id for c in self._clients if c is not self._client][0]
            self._db.set(security.__name__, "bounding_mask", security.SUPPORT)
            self._db.set(security.__name__, "support", [user_id])
            await self._db.set(main.__name__, "command_prefix", ["/"])
            return [("botmodule.py",
                     "angry-telegram/test/botmodule.py",
                     os.path.join(utils.get_module_dir(),
                                  "angry-telegram/test/botmodule.py"))]
        else:
            bot_id = [(await c.get_me(True)).user_id for c in self._clients if c is not self._client][0]
            self._db.set(security.__name__, "bounding_mask", -1)
            if stage == 0:
                self._db.set(security.__name__, "bounding_mask", -1)
                self._db.set(security.__name__, "owner", [bot_id])
                return [("usermodule.py",
                         "angry-telegram/test/usermodule.py",
                         os.path.join(utils.get_module_dir(),
                                      "angry-telegram/test/usermodule.py"))]
            self._db.set(security.__name__, "owner", [-1])
            if stage == 1:
                self._db.set(security.__name__, "sudo", [bot_id])
                return [("usermodule.py",
                         "angry-telegram/test/usermodule.py",
                         os.path.join(utils.get_module_dir(),
                                      "angry-telegram/test/usermodule.py"))]
            if stage == 2:
                self._db.set(security.__name__, "sudo", [])
                self._db.set(security.__name__, "support", [bot_id])
                return [("usermodule.py",
                         "angry-telegram/test/usermodule.py",
                         os.path.join(utils.get_module_dir(),
                                      "angry-telegram/test/usermodule.py"))]
            if stage == 3:
                self._db.set(security.__name__, "support", [])
                return [("usermodule.py",
                         "angry-telegram/test/usermodule.py",
                         os.path.join(utils.get_module_dir(),
                                      "angry-telegram/test/usermodule.py"))]
            if stage == 4:
                self._db.set(security.__name__, "owner", [bot_id])
                await self._db.set(security.__name__, "bounding_mask", 1)
                modules_files = []
                root_dir = os.path.join(utils.get_base_dir(), loader.MODULES_NAME)
                for address, _, files in os.walk(root_dir):
                    for file in files:
                        filepath = os.path.join(address, file)
                        rel_dir = os.path.relpath(address, utils.get_module_dir())
                        rel_file = os.path.join(rel_dir, file)

                        modules_files.append((file, rel_file, filepath))
                mods = filter(lambda x: (len(x[0]) > 3 and x[0][-3:] == ".py" and x[0][0] != "_"), modules_files)
                return [("usermodule.py",
                         "angry-telegram/test/usermodule.py",
                         os.path.join(utils.get_module_dir(),
                                      "angry-telegram/test/usermodule.py"))] + list(mods)

    def should_restart(self):
        TestManager.restart = asyncio.Future()  # reset
        return self._db.get(__name__, "stage", 0) <= 4
