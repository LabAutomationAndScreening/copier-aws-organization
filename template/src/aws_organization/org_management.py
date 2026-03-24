from lab_auto_pulumi import UserInfo  # noqa: F401 # remove this noqa when first used

from .lib import OrgAdmin


def get_org_admins() -> list[OrgAdmin]:
    """Define Admins.

    Example:
    ```
    org_admins: list[OrgAdmin] = [
        OrgAdmin(user_info=UserInfo(username="eli.fine@lab-sync.com"), enable_break_glass_access=False),
        OrgAdmin(user_info=UserInfo(username="mal.reynolds@firefly.star")),
    ]
    ```
    """
    org_admins: list[OrgAdmin] = []
    return org_admins
