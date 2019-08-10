import aiohttp
import logging
import json

from .api_wrapper import APIWrapper
from . import errors

log = logging.getLogger("laggron.nsfw")


class PahealPost:
    def __init__(self, data: dict):
        self.id = data["@id"]
        self.file_url = data["@file_url"]
        self.rating = data["@rating"]
        self.date = data["@date"]
        self.tags = data["@tags"]
        self.source = data["@source"]
        self.score = data["@score"]
        # self.md5 = data["@md5"]
        # self.file_name = data["@file_name"]
        # self.height = data["@height"]
        # self.width = data["@width"]
        # self.preview_url = data["@preview_url"]
        # self.preview_height = data["@preview_height"]
        # self.preview_width = data["@preview_width"]
        # self.is_warehoused = data["@is_warehoused"]
        # self.author = data["@author"]


class Paheal(APIWrapper):
    def __init__(self, session: aiohttp.client.ClientSession):
        super().__init__(session)
        self.base_link = "https://rule34.paheal.net/api/danbooru/find_posts/index.xml"

    async def get_images(self, tags: list = None):
        params = {"limit": 100, "tags": "+".join(tags)}
        response = await self.request(params, content_type="xml")
        if not response:
            raise errors.NotFound
        if response["posts"]["@count"] == "0":
            raise errors.NotFound
        return [PahealPost(x) for x in response["posts"]["post"]]
