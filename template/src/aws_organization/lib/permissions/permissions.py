from collections.abc import Callable
from typing import Any
from typing import override

from pulumi import ComponentResource
from pulumi import ResourceOptions
from pulumi_aws import identitystore as identitystore_classic
from pulumi_aws import ssoadmin
from pulumi_aws.iam import GetPolicyDocumentStatementArgs
from pulumi_aws.iam import get_policy_document
from pydantic import BaseModel
from pydantic import Field

from ..shared_lib import AwsAccountInfo
from ..shared_lib import AwsLogicalWorkload
from .lib import ORG_INFO
from .lib import UserAttributes
from .lib import UserInfo
from .lib import Username
from .lib import create_read_state_inline_policy

_all_users: dict[Username, UserAttributes] = {}


def lookup_user_id(username: Username) -> str:
    """Convert a username name into an AWS SSO User ID."""
    return identitystore_classic.get_user(
        alternate_identifier=identitystore_classic.GetUserAlternateIdentifierArgs(
            unique_attribute=identitystore_classic.GetUserAlternateIdentifierUniqueAttributeArgs(
                attribute_path="UserName", attribute_value=username
            )
        ),
        identity_store_id=ORG_INFO.identity_store_id,
    ).user_id


class AwsSsoPermissionSet(ComponentResource):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        managed_policies: list[str] | None = None,
        inline_policy: str | None = None,
    ):
        super().__init__("labauto:AwsSsoPermissionSet", name, None)
        if managed_policies is None:
            managed_policies = []
        self.name = name
        permission_set = ssoadmin.PermissionSet(
            name,
            instance_arn=ORG_INFO.sso_instance_arn,
            name=name,
            description=description,
            session_duration="PT12H",
            opts=ResourceOptions(parent=self),
        )
        self.permission_set_arn = permission_set.arn
        for policy_name in managed_policies:
            _ = ssoadmin.ManagedPolicyAttachment(
                f"{name}-{policy_name}",
                instance_arn=ORG_INFO.sso_instance_arn,
                managed_policy_arn=f"arn:aws:iam::aws:policy/{policy_name}",
                permission_set_arn=self.permission_set_arn,
                opts=ResourceOptions(parent=self),
            )
        if inline_policy is not None:
            _ = ssoadmin.PermissionSetInlinePolicy(
                f"{name}-inline-policy",
                instance_arn=ORG_INFO.sso_instance_arn,
                permission_set_arn=self.permission_set_arn,
                inline_policy=inline_policy,
                opts=ResourceOptions(parent=self),
            )
        self.register_outputs(
            {
                "permission_set_arn": self.permission_set_arn,
            }
        )


class AwsSsoPermissionSetContainer(BaseModel):
    name: str
    description: str
    managed_policies: list[str] = Field(
        default_factory=list,
        max_length=10,  # AWS default limit
    )
    inline_policy_callable: Callable[[], str] | None = None
    _permission_set: AwsSsoPermissionSet | None = None

    def create_permission_set(self, inline_policy: str | None = None) -> AwsSsoPermissionSet:
        if inline_policy is None and self.inline_policy_callable is not None:
            inline_policy = self.inline_policy_callable()  # TODO: unit test this
        self._permission_set = AwsSsoPermissionSet(
            name=self.name,
            description=self.description,
            managed_policies=self.managed_policies,
            inline_policy=inline_policy,
        )
        return self._permission_set

    @property
    def permission_set(self) -> AwsSsoPermissionSet:
        assert self._permission_set is not None
        return self._permission_set


def create_manual_secrets_entry_inline_policy() -> str:
    return get_policy_document(
        statements=[
            GetPolicyDocumentStatementArgs(
                sid="AllResources",
                effect="Allow",
                actions=[
                    "secretsmanager:ListSecrets",  # when trying to use `secretsmanager:Name` and `secretsmanager:SecretId` to restrict this, it wouldn't let any be listed
                ],
                resources=["*"],
            ),
            GetPolicyDocumentStatementArgs(
                sid="SpecificSecrets",
                effect="Allow",
                actions=[
                    "secretsmanager:DescribeSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:ListSecretVersionIds",
                    "secretsmanager:PutSecretValue",
                ],
                resources=["arn:aws:secretsmanager:*:*:secret:/manually-entered-secrets/*"],
            ),
        ]
    ).json


MANUAL_SECRETS_ENTRY_PERM_SET_CONTAINER = (
    AwsSsoPermissionSetContainer(  # TODO: set relay state to SecretsManager landing page
        name="ManualSecretsEntry",
        description="The ability to manually update secrets into the secrets manager.",
        inline_policy_callable=create_manual_secrets_entry_inline_policy,
    )
)
LOW_RISK_ADMIN_PERM_SET_CONTAINER = AwsSsoPermissionSetContainer(
    name="LowRiskAccountAdminAccess",
    description="Low Risk Account Admin Access",
    managed_policies=["AdministratorAccess"],
)

VIEW_ONLY_PERM_SET_CONTAINER = AwsSsoPermissionSetContainer(
    name="ViewOnlyAccess",
    description="The ability to view logs and other resource details in protected environments for troubleshooting.",
    managed_policies=[
        "AWSSupportAccess",  # Allow users to request AWS support for technical questions.
        "job-function/ViewOnlyAccess",  # wide ranging attribute view access across a variety of services
        "CloudWatchReadOnlyAccess",  # be able to read CloudWatch logs/metrics/etc
        "AmazonSSMReadOnlyAccess",  # look at SSM fleet/hybrid activation details
        "AWSLambda_ReadOnlyAccess",  # review traces and logs for debugging Lambdas easily through the console
        "AmazonEventBridgeReadOnlyAccess",  # see basic metrics about Event Bridges to troubleshoot
        "AmazonEC2ContainerRegistryReadOnly",  # describe ECR images,
        "AWSBillingReadOnlyAccess",  # view billing information to help optimize costs
        "CostOptimizationHubReadOnlyAccess",  # view actual costs and usage
        # TODO: figure out how to add back in AmazonEventBridgeSchemasReadOnlyAccess permission...but we're at the limit of managed policies that can be attached currently
        # TODO: figure out how to add back in "AmazonAppStreamReadOnlyAccess",  # look at the details of stack/fleet information to troubleshoot any issues
        # TODO: "CloudWatchEventsReadOnlyAccess",  # see information about event rules and patterns
    ],
    inline_policy_callable=create_read_state_inline_policy,
)


def _create_unique_userinfo_list(users: list[UserInfo]) -> list[UserInfo]:
    unique_user_infos: dict[Username, UserInfo] = {}
    for user_info in users:
        if user_info.username not in unique_user_infos:
            unique_user_infos[user_info.username] = user_info
            continue
        info_in_dict = unique_user_infos[user_info.username]
        if user_info == info_in_dict:
            continue
        raise ValueError(f"Duplicate user info for {user_info!r} and {info_in_dict!r}")  # noqa: TRY003 # not worth creating a custom exception until we test this # TODO: unit test this
    return list(unique_user_infos.values())


class AwsSsoPermissionSetAccountAssignments(ComponentResource):
    def __init__(
        self,
        *,
        account_info: AwsAccountInfo,
        permission_set: AwsSsoPermissionSet,
        users: list[UserInfo] | None = None,
    ):
        if users is None:
            users = []
        resource_name = f"{permission_set.name}-{account_info.name}"
        super().__init__(
            "labauto:AwsSsoPermissionSetAccountAssignments",
            resource_name,
            None,
        )
        user_infos = _create_unique_userinfo_list(users)

        for user_info in user_infos:
            _ = ssoadmin.AccountAssignment(
                f"{resource_name}-{user_info.username}",
                instance_arn=ORG_INFO.sso_instance_arn,
                permission_set_arn=permission_set.permission_set_arn,
                principal_id=lookup_user_id(user_info.username),
                principal_type="USER",
                target_id=account_info.id,
                target_type="AWS_ACCOUNT",
                opts=ResourceOptions(parent=self),
            )


class DefaultWorkloadPermissionAssignments(BaseModel):
    workload_info: AwsLogicalWorkload
    users: list[UserInfo] | None = None

    @override
    def model_post_init(self, _: Any) -> None:
        for protected_env_account in [*self.workload_info.prod_accounts, *self.workload_info.staging_accounts]:
            _ = AwsSsoPermissionSetAccountAssignments(
                account_info=protected_env_account,
                permission_set=VIEW_ONLY_PERM_SET_CONTAINER.permission_set,
                users=self.users,
            )
        for unprotected_env_account in self.workload_info.dev_accounts:
            _ = AwsSsoPermissionSetAccountAssignments(
                account_info=unprotected_env_account,
                permission_set=LOW_RISK_ADMIN_PERM_SET_CONTAINER.permission_set,
                users=self.users,
            )


def create_org_admin_permissions(
    *, workloads_dict: dict[str, AwsLogicalWorkload], users: list[UserInfo] | None = None
) -> None:
    view_only_permission_set = VIEW_ONLY_PERM_SET_CONTAINER.permission_set
    manual_secrets_entry_permission_set = MANUAL_SECRETS_ENTRY_PERM_SET_CONTAINER.permission_set

    _ = AwsSsoPermissionSetAccountAssignments(
        account_info=workloads_dict["central-infra"].prod_accounts[0],
        permission_set=view_only_permission_set,
        users=users,
    )
    _ = AwsSsoPermissionSetAccountAssignments(
        account_info=workloads_dict["central-infra"].prod_accounts[0],
        permission_set=manual_secrets_entry_permission_set,
        users=users,
    )
    _ = AwsSsoPermissionSetAccountAssignments(
        account_info=workloads_dict["identity-center"].prod_accounts[0],
        permission_set=view_only_permission_set,
        users=users,
    )

    _ = AwsSsoPermissionSetAccountAssignments(
        account_info=workloads_dict["billing-delegate"].prod_accounts[0],
        permission_set=view_only_permission_set,
        users=users,
    )
