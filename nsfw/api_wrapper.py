import aiohttp
import logging
import xmltodict

from . import errors

log = logging.getLogger("laggron.nsfw")
errors_map = {
    400: errors.BadRequest,
    403: errors.Forbidden,
    404: errors.NotFound,
}

class APIWrapper:

    def __init__(self, session: aiohttp.client.ClientSession):
        self.session = session
        self.base_link = None
    
    async def request(self, parameters: dict = None, content_type: str = "json"):
        log.debug(f"GET request to {self.base_link} with the following parameters: {parameters}")
        async with self.session.get(self.base_link, params=parameters) as response:
            if response.status >= 400:
                log.error(
                    f"Unexpected error with {self.base_link}, status code: {response.status}, "
                    f"full output: {await response.text()}"
                )
                raise errors_map.get(response.status, d=errors.APIException)
            if content_type == "xml":
                text = await response.text()
                return xmltodict.parse(text)
            else:
                return await response.json()
