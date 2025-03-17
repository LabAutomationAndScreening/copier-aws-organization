import logging
import time
from typing import Any
from typing import override

from ephemeral_pulumi_deploy.utils import common_tags_native
from pulumi import ComponentResource
from pulumi import Resource
from pulumi import ResourceOptions
from pulumi import dynamic
from pulumi import export
from pulumi.dynamic import CreateResult
from pulumi_aws_native import organizations

from .constants import ACCOUNT_EMAIL_DOMAIN
from .constants import ACCOUNT_EMAIL_PREFIX

logger = logging.getLogger(__name__)


class SleepProvider(dynamic.ResourceProvider):
    serialize_as_secret_always = False

    @override
    def create(self, props: dict[str, Any]) -> CreateResult:
        duration = props["seconds"]
        time.sleep(duration)
        return CreateResult(id_="sleep-done", outs={})


class Sleep(dynamic.Resource):
    def __init__(self, name: str, seconds: float, opts: ResourceOptions | None = None):
        super().__init__(SleepProvider(), name, props={"seconds": seconds}, opts=opts)


class AwsAccount(ComponentResource):
    def __init__(self, *, account_name: str, ou: organizations.OrganizationalUnit, parent: Resource | None = None):
        super().__init__("labauto:aws-organization:AwsAccount", account_name, None, opts=ResourceOptions(parent=parent))
        self.account = organizations.Account(
            account_name,
            opts=ResourceOptions(parent=self),
            account_name=account_name,
            email=f"{ACCOUNT_EMAIL_PREFIX}+{account_name}@{ACCOUNT_EMAIL_DOMAIN}",
            parent_ids=[ou.id],
            # Deliberately not setting the role_name here, as it causes problems during any subsequent updates, even when not actually changing the role name. Could possible set up ignore_changes...but just leaving it out for now
            tags=common_tags_native(),
        )
        self.wait_after_account_create = Sleep(
            f"wait-after-account-create-{account_name}",
            60 * 5,  # only waiting 1 minute seemed to sometimes cause problems
            opts=ResourceOptions(parent=self, depends_on=[self.account]),
        )
        self.account_info_kwargs = self.account.id.apply(lambda account_id: {"id": account_id, "name": account_name})

        export(f"{account_name}-account-id", self.account.id)
        export(f"{account_name}-role-name", self.account.role_name)
