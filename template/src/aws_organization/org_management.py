from lab_auto_pulumi import UserInfo
from pydantic import BaseModel


class OrgAdmin(BaseModel):
    user_info: UserInfo
    enable_break_glass_access: bool = False


def get_org_admins() -> list[OrgAdmin]:
    """Define Admins.

    Example:
    ```
    org_admins: list[OrgAdmin] = [
        OrgAdmin(user_info=UserInfo(username="eli.fine@elifine.com"), enable_break_glass_access=False),
        OrgAdmin(user_info=UserInfo(username="mal.reynolds@firefly.star")),
    ]
    ```
    """
    org_admins: list[OrgAdmin] = []
    return org_admins
