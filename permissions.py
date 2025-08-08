from discord import Member

from config import PermissionsConfig


def has_moderator_role(member: Member, config: PermissionsConfig) -> bool:
    if config.mod_role_id or config.supermod_role_id:
        role_ids = {role.id for role in member.roles}
        if config.mod_role_id and config.mod_role_id in role_ids:
            return True
        if config.supermod_role_id and config.supermod_role_id in role_ids:
            return True
        return False

    role_names = {role.name.lower() for role in member.roles}
    return ("mod" in role_names) or ("supermod" in role_names)


def is_admin(member: Member, config: PermissionsConfig) -> bool:
    if config.admin_role_id:
        return config.admin_role_id in {role.id for role in member.roles}
    return getattr(member.guild_permissions, "administrator", False)


