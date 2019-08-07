import aiohttp
import logging

from .api_wrapper import APIWrapper
from . import errors

log = logging.getLogger("laggron.nsfw")


class Rule34Post:
    def __init__(self, data: dict):
        self.height = data["@height"]
        self.score = data["@score"]
        self.file_url = data["@file_url"]
        self.parent_id = data["@parent_id"]
        self.sample_url = data["@sample_url"]
        self.sample_width = data["@sample_width"]
        self.sample_height = data["@sample_height"]
        self.preview_url = data["@preview_url"]
        self.rating = data["@rating"]
        self.tags = data["@tags"]
        self.id = data["@id"]
        self.width = data["@width"]
        self.change = data["@change"]
        self.md5 = data["@md5"]
        self.creator_id = data["@creator_id"]
        self.has_children = data["@has_children"]
        self.created_at = data["@created_at"]
        self.status = data["@status"]
        self.source = data["@source"]
        self.has_notes = data["@has_notes"]
        self.has_comments = data["@has_comments"]
        self.preview_width = data["@preview_width"]
        self.preview_height = data["@preview_height"]


class Rule34(APIWrapper):
    def __init__(self, session: aiohttp.client.ClientSession):
        super().__init__(session)
        self.base_link = "https://rule34.xxx/index.php"

    async def get_images(self, tags: list = None):
        params = {
            "page": "dapi",
            "s": "random",
            "q": "index",
            "rating": "explicit",
        }
        if tags:
            params["tags"] = "+".join(tags)
        response = await self.request(params, content_type="xml")
        log.debug(response)
        if response["posts"]["@count"] == "0":
            raise errors.NotFound
        return [Rule34Post(x) for x in response["posts"]["post"]]
