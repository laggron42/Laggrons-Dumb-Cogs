import aiohttp
import logging

from .api_wrapper import APIWrapper
from . import errors

log = logging.getLogger("laggron.nsfw")


class DanbooruPost:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.created_at = data["created_at"]
        self.uploader_id = data["uploader_id"]
        self.score = data["score"]
        self.source = data["source"]
        self.rating = data["rating"]
        self.tag_string = data["tag_string"]
        self.fav_count = data["fav_count"]
        self.up_score = data["up_score"]
        self.down_score = data["down_score"]
        self.uploader_name = data["uploader_name"]
        self.has_large = data["has_large"]
        self.tag_string_general = data["tag_string_general"]
        self.tag_string_character = data["tag_string_character"]
        self.tag_string_copyright = data["tag_string_copyright"]
        self.tag_string_artist = data["tag_string_artist"]
        self.tag_string_meta = data["tag_string_meta"]
        self.file_url = data["file_url"]
        self.large_file_url = data["large_file_url"]


class Danbooru(APIWrapper):
    def __init__(self, session: aiohttp.client.ClientSession):
        super().__init__(session)
        self.base_link = "https://danbooru.donmai.us/posts.json"

    async def get_images(self, tags: list = None):
        params = {"limit": 100, "tags": "+".join(tags), "random": "true"}
        response = await self.request(params)
        if not response:
            raise errors.NotFound
        return [DanbooruPost(x) for x in response]
