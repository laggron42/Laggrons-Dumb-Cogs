import aiohttp
import logging

from .api_wrapper import APIWrapper
from . import errors

log = logging.getLogger("laggron.nsfw")


class e621Post:
    
    def __init__(self, data: dict):
        self.tags = data["tags"]
        self.description = data["description"]
        self.author = data["author"]
        self.source = data["source"]
        self.score = data["score"]
        self.fav_count = data["fav_count"]
        self.file_url = data["file_url"]
        self.rating = data["rating"]
        self.artist = data["artist"]

class e621(APIWrapper):

    def __init__(self, session: aiohttp.client.ClientSession):
        super().__init__(session)
        self.base_link = "https://e621.net/post/index.json"
    
    async def get_images(self, tags: list = None):
        params = {
            "limit": 100,
            "tags": "+".join(tags),
        }
        response = await self.request(params)
        if not response:
            raise errors.NotFound
        return [e621Post(x) for x in response]
