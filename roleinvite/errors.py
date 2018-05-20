class Errors:
    """
    Custom error handling used for the cog and the API
    """

    def __init__(self, exception):
        pass

    # errors used in the API
    class EmptyRolesList:
        """
        The list of roles that needs to be linked to an invite is empty.
        """
        pass

    class NotInvite:
        """
        The invite sent is not found as a discord.Invite object.
        """

    class InviteNotFound:
        """
        The invite sent isn't in the guild's invite list.
        """
        pass

    # errors used in the listener
    class CannotGetInvites:
        """
        The bot isn't allowed to get the guild invites.
        Manage server permission is needed.
        """
        pass

    class CannotAddRole:
        """
        The bot isn't allowed to give a role. 
        The role hierarchy was modified or a 3rd party module added the role without check.
        """
        pass
