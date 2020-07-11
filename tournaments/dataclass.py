from datetime import datetime, timedelta
from typing import Optional


class ChallongeTournament:
    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.game: str = data["game"]
        self.url: str = data["url"]
        self.id: str = data["id"]
        self.limit: Optional[int] = data["limit"]
        self.status: str = data["status"]
        self.tournament_start: datetime = datetime.fromtimestamp(int(data["tournament_start"]))
        if data["register_start"]:
            self.register_start: datetime = datetime.fromtimestamp(int(data["register_start"]))
        else:
            self.register_start = None
        if data["register_stop"]:
            self.register_stop: datetime = datetime.fromtimestamp(int(data["register_stop"]))
        else:
            self.register_stop = None
        if data["checkin_start"]:
            self.checkin_start: datetime = datetime.fromtimestamp(int(data["checkin_start"]))
        else:
            self.checkin_start = None
        if data["checkin_stop"]:
            self.checkin_stop: datetime = datetime.fromtimestamp(int(data["checkin_stop"]))
        else:
            self.checkin_stop = None

    @classmethod
    def from_challonge_data(
        cls,
        data: dict,
        register_start: int,
        register_stop: int,
        checkin_start: int,
        checkin_stop: int,
    ):
        self = cls.__new__(cls)  # doing this will instanciate the class without calling __init__
        self.name: str = data["name"]
        self.game: str = data[
            "game_name"
        ].title()  # Non-recognized games are lowercase for Challonge
        self.url: str = data["full_challonge_url"]
        self.id: str = data["id"]
        self.limit: str = data["signup_cap"]
        self.status: str = data["state"]
        self.tournament_start: datetime = data["start_at"]
        if register_start != 0:
            self.register_start: datetime = self.tournament_start - timedelta(hours=register_start)
        else:
            self.register_start = None
        if register_stop != 0:
            self.register_stop: datetime = self.tournament_start - timedelta(minutes=register_stop)
        else:
            self.register_stop = None
        if checkin_start != 0:
            self.checkin_start: datetime = self.tournament_start - timedelta(minutes=checkin_start)
        else:
            self.checkin_start = None
        if checkin_stop != 0:
            self.checkin_stop: datetime = self.tournament_start - timedelta(minutes=checkin_stop)
        else:
            self.checkin_stop = None
        return self

    def to_dict(self) -> dict:
        """Returns a dict ready for Config."""
        data = {
            "name": self.name,
            "game": self.game,
            "url": self.url,
            "id": self.id,
            "limit": self.limit,
            "status": self.status,
            "tournament_start": int(self.tournament_start.timestamp()),
            "register_start": int(self.register_start.timestamp())
            if self.register_start
            else None,
            "register_stop": int(self.register_stop.timestamp()) if self.register_stop else None,
            "checkin_start": int(self.checkin_start.timestamp()) if self.checkin_start else None,
            "checkin_stop": int(self.checkin_stop.timestamp()) if self.checkin_stop else None,
        }
        return data
