import asyncio
import random
import discord
import pytest
import weakref

from pathlib import Path
from datetime import datetime, timedelta
from discord.mixins import Hashable
from typing import TYPE_CHECKING

from redbot.core import Config
from redbot.core import config as config_module, drivers
from redbot.core.bot import Red

from redbot import _update_event_loop_policy
from redbot.pytest import empty_role, empty_message

if TYPE_CHECKING:
    from pytest_mock.plugin import MockerFixture
    from _pytest.fixtures import SubRequest
    from _pytest.monkeypatch import MonkeyPatch

_update_event_loop_policy()


class Hashable(Hashable):
    def __init__(self) -> None:
        self.id = random.randint(10000000000000000, 999999999999999999)


# fixtures from redbot.core.pytest but with scopes
@pytest.fixture(scope="session")
def event_loop(request):
    """Create an instance of the default event loop for entire session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    asyncio.set_event_loop(None)
    loop.close()


@pytest.fixture(scope="session")
def override_data_path(tmpdir_factory):
    from redbot.core import data_manager
    import uuid

    rand = str(uuid.uuid4())
    data_manager.basic_config = data_manager.basic_config_default
    data_manager.basic_config["DATA_PATH"] = str(tmpdir_factory.mktemp(rand))


@pytest.fixture(scope="session")
def driver(tmpdir_factory, override_data_path):
    import uuid

    rand = str(uuid.uuid4())
    path = Path(str(tmpdir_factory.mktemp(rand)))
    return drivers.get_driver("PyTest", str(random.randint(1, 999999)), data_path_override=path)


@pytest.fixture(scope="session")
def config(driver):
    config_module._config_cache = weakref.WeakValueDictionary()
    conf = Config(cog_name="PyTest", unique_identifier=driver.unique_cog_identifier, driver=driver)
    yield conf


@pytest.fixture(scope="session")
def config_fr(driver):
    """
    Mocked config object with force_register enabled.
    """
    config_module._config_cache = weakref.WeakValueDictionary()
    conf = Config(
        cog_name="PyTest",
        unique_identifier=driver.unique_cog_identifier,
        driver=driver,
        force_registration=True,
    )
    yield conf


@pytest.fixture(scope="session")
def red(config_fr):
    from redbot.core.cli import parse_cli_flags

    cli_flags = parse_cli_flags(["ignore_me"])

    description = "Red v3 - Alpha"

    Config.get_core_conf = lambda *args, **kwargs: config_fr

    red = Red(cli_flags=cli_flags, description=description, dm_help=None, owner_ids=set())

    yield red


@pytest.fixture(autouse=True)
def init_mocker(mocker: "MockerFixture", empty_message):
    mocker.patch.object(discord.abc.Messageable, "send", return_value=empty_message)


@pytest.fixture(scope="package")
def guild_factory(channel_factory, category_factory, role_factory, _member_factory):
    member_factory = _member_factory

    class Guild(Hashable):
        me = None
        default_role = empty_role
        categories = []

        def get_channel(self, id):
            if not id:
                return None
            channel = channel_factory.get(id)
            channel.guild = self
            return channel

        def get_category(self, id):
            # doesn't exist in Guild but we need it for assertions
            if not id:
                return None
            category = category_factory.get(id)
            category.guild = self
            return category

        def get_role(self, id):
            if not id:
                return None
            role = role_factory.get(id)
            role.guild = self
            return role

        def get_member(self, id):
            if not id:
                return None
            member = member_factory.get(id)
            member.guild = self
            return member

        async def create_text_channel(self, *args, category=None, **kwargs):
            channel = channel_factory.get()
            channel.guild = self
            if category:
                channel.position = len(category.channels) + 1
                category.channels.append(channel)
            return channel

        async def create_category(self, *args, **kwargs):
            category = category_factory.get()
            category.guild = self
            category.position = len(self.categories) + 1
            self.categories.append(category)
            return category

    class GuildFactory:
        def get(self):
            n = Guild()
            n.me = member_factory.get(guild=n)
            return n

    return GuildFactory()


@pytest.fixture(scope="package")
def guild(guild_factory):
    return guild_factory.get()


@pytest.fixture(scope="package")
def member_factory(request: "SubRequest", package_mocker: "MockerFixture"):
    class User(Hashable):
        name = "Empty user"

        async def send(self, *args, **kwargs):
            pass

        async def create_dm(self, *args, **kwargs):
            return package_mocker.Mock()

    class Member:
        name = "Empty member"
        nick = None
        guild = None
        _roles = []
        joined_at = datetime.now() - timedelta(days=random.randint(1, 999))
        premium_since = None
        _client_status = {}
        activities = []
        _state = None
        _user = None

        def __init__(self):
            self._user = User()
            self.send = self._user.send
            mock = package_mocker.patch.object(self, "_state", autospec=True)
            mock.http = package_mocker.AsyncMock()

        @property
        def id(self):
            return self._user.id

        @id.setter
        def id(self, value):
            self._user.id = value

        def __str__(self):
            return "Empty member#0000"

        async def add_roles(self, *args, **kwargs):
            pass

        async def remove_roles(self, *args, **kwargs):
            pass

    class MemberFactory:
        def get(self, id=None, guild=None):
            n = Member()
            if id:
                n.id = id
            if guild:
                n.guild = guild
            else:
                n.guild = request.getfixturevalue("guild")
            return n

    return MemberFactory()


_member_factory = member_factory


@pytest.fixture()
def member(member_factory):
    return member_factory.get()


@pytest.fixture(scope="package", params=[False, True])
def maybe_patch_member(
    request: "SubRequest", session_mocker: "MockerFixture", raise_http_error, member_factory
):
    """
    Return two members, where one will refuse DMs (fixture to be returned twice).
    """

    def patch(member: discord.Member = None):
        member = member or member_factory.get()
        if request.param:
            mock = session_mocker.patch.object(member, "send")
            mock.side_effect = raise_http_error(
                discord.Forbidden,
                403,
                "Forbidden",
                "Cannot send messages to this user",
            )
        return member

    return patch


@pytest.fixture(scope="package")
def channel_factory(message_factory):
    class Channel(Hashable):
        name = "empty-channel"
        guild = None
        position = 0
        mention = f"<#{id}>"

        def __str__(self):
            return "empty-channel"

        async def delete(self, *args, **kwargs):
            return

        async def send(self, *args, **kwargs):
            return message_factory.get()

        async def set_permissions(self, *args, **kwargs):
            return

    class ChannelFactory:
        def get(self, id=None):
            n = Channel()
            if id:
                n.id = id
            return n

    return ChannelFactory()


@pytest.fixture()
def channel(channel_factory):
    return channel_factory.get()


@pytest.fixture(scope="package")
def role_factory():
    class Role(Hashable):
        name = "Empty role"
        guild = None
        position = 0
        mention = f"<@{id}>"

        def __str__(self):
            return "Empty role"

    class RoleFactory:
        def get(self, id=None):
            n = Role()
            if id:
                n.id = id
            return n

    return RoleFactory()


@pytest.fixture()
def role(role_factory):
    return role_factory.get()


@pytest.fixture(scope="package")
def category_factory():
    class Category(Hashable):
        name = "Empty Category"
        guild = None
        channels = []
        position = 0

        def __str__(self):
            return "Empty Category"

        async def edit(self, *args, **kwargs):
            return

    class CategoryFactory:
        def get(self, id=None):
            n = Category()
            if id:
                n.id = id
            return n

    return CategoryFactory()


@pytest.fixture()
def category(category_factory):
    return category_factory.get()


@pytest.fixture(scope="package")
def message_factory():
    class Message(Hashable):
        content = "Empty Message"
        guild = None
        channel = None

        async def pin(self, *args, **kwargs):
            return

        async def edit(self, *args, **kwargs):
            return

    class MessageFactory:
        def get(self, id=None):
            n = Message()
            if id:
                n.id = id
            return n

    return MessageFactory()


@pytest.fixture()
def message(message_factory):
    return message_factory.get()


@pytest.fixture(scope="package")
def ctx_factory(member_factory, channel_factory, message_factory, guild, red):
    _guild = guild

    class Context:
        author = member_factory.get()
        guild = _guild
        channel = channel_factory.get()
        message = message_factory.get()
        bot = red
        clean_prefix = "!"

        async def send(self, *args):
            return empty_message

        async def tick(self):
            pass

    class ContextFactory:
        def get(self):
            return Context()

    return ContextFactory()


@pytest.fixture()
def ctx(ctx_factory):
    return ctx_factory.get()


@pytest.fixture(scope="package")
def raise_http_error(session_mocker: "MockerFixture"):
    def wrapper(
        exception=discord.HTTPException,
        status: int = 500,
        reason: str = "Internal Server Error",
        text: str = "Testing HTTP failure",
    ):
        exc = exception(session_mocker.Mock(status=status, reason=reason), text)

        def error(*args, **kwargs):
            def maybe_log(*args, **kwargs):
                exception = kwargs.get("exc_info", None)
                if exception is None or not isinstance(exception, type(exc)):
                    return session_mocker.DEFAULT

            mock_log = session_mocker.patch("tournaments.objects.base.log")
            mock_log.log.side_effect = maybe_log
            raise exc

        return error

    return wrapper
