# Most, if not all of these functions were taken from the audio cog.
# If they're here, they couldn't be directly imported for implementation reasons

from redbot.core import audio


# https://github.com/Cog-Creators/Red-DiscordBot/blob/b05933274a11fb097873ab0d1b246d37b06aa306/
# redbot/cogs/audio/core/utilities/formatting.py#L394-L412
def draw_time(player: audio.Player) -> str:
    paused = player.paused
    pos = player.position or 1
    dur = getattr(player.current, "length", pos)
    sections = 12
    loc_time = round((pos / dur if dur != 0 else pos) * sections)
    bar = "\N{BOX DRAWINGS HEAVY HORIZONTAL}"
    seek = "\N{RADIO BUTTON}"
    if paused:
        msg = "\N{DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}"
    else:
        msg = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"
    for i in range(sections):
        if i == loc_time:
            msg += seek
        else:
            msg += bar
    return msg


# https://github.com/Cog-Creators/Red-DiscordBot/blob/6c4e5af5ee85a8c9f3930d70667d6f814c4547b2/
# redbot/cogs/audio/core/utilities/miscellaneous.py#L260-L274
def format_time(time: int) -> str:
    """ Formats the given time into DD:HH:MM:SS """
    seconds = time / 1000
    days, seconds = divmod(seconds, 24 * 60 * 60)
    hours, seconds = divmod(seconds, 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    day = ""
    hour = ""
    if days:
        day = "%02d:" % days
    if hours or day:
        hour = "%02d:" % hours
    minutes = "%02d:" % minutes
    sec = "%02d" % seconds
    return f"{day}{hour}{minutes}{sec}"