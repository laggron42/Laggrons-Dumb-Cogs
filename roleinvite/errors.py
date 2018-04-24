class Errors:
    """Custom error handling used for the API"""

    class EmptyRolesList(Exception):
        """
        The list of roles that needs to be linked to an invite is empty.
        """
        pass

    class WrongInviteObject(Exception):
        """
        The invite object wasn't get using the good way. It can't get its number of uses. 
        It need to be get using guild.invites() and discord.utils.get().
        Not using Client.get_invite()
        """
        pass

    class InviteNotFound(Exception):
        """
        The invite sent isn't in the guild's invite list.
        """
        pass

    class CannotGetInvites():
        """
        The bot isn't allowed to get the guild invites.
        Manage server permission is needed.
        """
        pass