import aiohttp
import logging

from urllib.parse import quote
from datetime import datetime
from typing import Optional

log = logging.getLogger("red.laggron.codmw")
BASE_URL = "https://my.callofduty.com/api/papi-client/"


class HTTPException(Exception):
    """
    The API Returned an error code.
    """

    def __init__(self, data):
        try:
            type = data["data"]["type"]
            message = data["data"]["message"]
        except KeyError:
            type = data["error"]
            message = data["message"]
        super().__init__(f"{type}: {message}")
        self.type = type
        self.message = message


class Forbidden(HTTPException):
    """
    Unauthorized call
    """

    pass


class NotFound(HTTPException):
    """
    Player not found.
    """

    pass


class Client:
    """
    The base client for a connexion to the COD API.

    Parameters
    ----------
    game: str
        The game you want to pull the information for (options: 'mw', 'wwii', 'bo4')
    username: str
        Username used for authentification.
    password: str
        Password used for authentification.
    cookies: Optional[dict]
        A dict of cookies you can re-use from previous session. This prevents a new
        authentification, which can require a captcha after some requests.
    """

    def __init__(self, version: str, game: str, username: str, password: str, cookies: dict = {}):
        self.game = game
        self.credentials = {"username": username, "password": password}
        cookie_jar = aiohttp.CookieJar()
        cookie_jar.update_cookies(cookies)
        self.session = aiohttp.ClientSession(cookie_jar=cookie_jar)

    async def _get_tokens(self):
        log.debug("Cookies expired. Refreshing tokens...")
        credentials = self.credentials
        await self.session.get("https://profile.callofduty.com/cod/login")
        credentials["remember_me"] = True
        credentials["_csrf"] = self.session.cookie_jar._cookies["callofduty.com"][
            "XSRF-TOKEN"
        ].value
        form = aiohttp.FormData(fields=credentials)
        await self.session.post(
            "https://profile.callofduty.com/do_login?new_SiteId=cod", data=form
        )

    async def _request(self, type: str, url: str, data=None, **parameters):
        async with self.session.request(type, url=url, data=data, params=parameters) as response:
            if response.status >= 500:
                data = {"error": response.status, "message": response.reason}
                raise HTTPException(data)
            if response.content_type != "application/json":
                raise RuntimeError(
                    f"Expected json content type, received {response.content_type} instead"
                )
            data = await response.json()
            if data["status"] == "error":
                if data["data"]["message"] == "Not permitted: not authenticated":
                    raise Forbidden(data)
                elif data["data"]["message"] == "Not permitted: user not found":
                    raise NotFound(data)
                else:
                    raise HTTPException(data)
            if data["status"] == 404:
                raise NotFound(data)
            return data["data"]

    async def fetch_player_info(self, platform: str, username: str):
        """
        Pull a variaty of data from a certain player, this includes but is not limited to:

        *   Total suicides (lol)
        *   Accuracy
        *   Wins / losses
        *   KDR
        *   Stats for each seperate gamemode
        *   Time played total & for each seperate gamemode
        *   Score per minute
        *   Much, MUCH more...

        Parameters
        ----------
        platform: str
            The platform of the player (ex: battle, xbl, psn, steam)
        username: str
            A string of the player name as mentioned on the chosen platform

        Returns
        -------
        dict
            The informations fetched.
        """
        username = quote(username, safe="")
        url = BASE_URL + (
            "stats/cod/{version}/title/{game}/platform/{platform}/gamer/{username}/profile/type/mp"
        ).format(version="v1", game=self.game, platform=platform, username=username)
        return await self._request("GET", url)

    async def fetch_player_recent_matches(
        self,
        platform: str,
        username: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ):
        """
        Pull information about the recent matches this player was involved in,
        including stats collected during the game. By default the returned list
        is limited to the most recent 20 matches.

        Parameters
        ----------
        platform: str
            The platform of the player (ex: battle, xbl, psn, steam)
        username: str
            A string of the player name as mentioned on the chosen platform
        start: Optional[datetime.datetime]
            A utc timestamp of the start of the history you want to pull,
            use :py:obj:`None` to just pull most recent
        end: Optional[datetime.datetime]
            A utc timestamp of the end of the history you want to pull,
            use :py:obj:`None` to just pull most recent

        Returns
        -------
        dict
            The informations fetched.
        """
        start = start.timestamp() if start else 0
        end = end.timestamp() if end else 0
        username = quote(username, safe="")
        url = BASE_URL + (
            "crm/cod/{version}/title/{game}/platform/{platform}/gamer/{username}/"
            "matches/mp/start/{start}/end/{end}/details"
        ).format(
            version="v2",
            game=self.game,
            platform=platform,
            username=username,
            start=start,
            end=end,
        )
        return await self._request("GET", url)
