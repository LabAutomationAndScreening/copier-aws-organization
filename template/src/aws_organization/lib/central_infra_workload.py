import pulumi_aws
from ephemeral_pulumi_deploy import get_config
from ephemeral_pulumi_deploy.utils import common_tags
from ephemeral_pulumi_deploy.utils import common_tags_native
from ephemeral_pulumi_deploy.utils import get_aws_account_id
from lab_auto_pulumi import GITHUB_PREVIEW_TOKEN_SECRET_NAME
from lab_auto_pulumi import MANUAL_IAC_SECRETS_PREFIX
from lab_auto_pulumi import ORG_MANAGED_SSM_PARAM_PREFIX
from lab_auto_pulumi import WORKLOAD_INFO_SSM_PARAM_PREFIX
from lab_auto_pulumi import AwsAccountInfo
from lab_auto_pulumi import AwsLogicalWorkload
from pulumi import Output
from pulumi import ResourceOptions
from pulumi_aws.iam import GetPolicyDocumentStatementArgs
from pulumi_aws.iam import GetPolicyDocumentStatementConditionArgs
from pulumi_aws.iam import GetPolicyDocumentStatementPrincipalArgs
from pulumi_aws.iam import get_policy_document
from pulumi_aws_native import Provider
from pulumi_aws_native import ProviderAssumeRoleArgs
from pulumi_aws_native import iam
from pulumi_aws_native import s3
from pulumi_aws_native import ssm
from pulumi_command.local import Command

from .account import AwsAccount
from .constants import CENTRAL_INFRA_GITHUB_ORG_NAME
from .constants import CENTRAL_INFRA_REPO_NAME
from .org_units import OrganizationalUnits
from .workload import DEFAULT_ORG_ACCESS_ROLE_NAME
from .workload import CommonWorkloadKwargs
from .workload import create_pulumi_kms_role_policy_args


def create_central_infra_workload(org_units: OrganizationalUnits) -> tuple[CommonWorkloadKwargs, Command]:
    central_infra_workload_name = "central-infra"  # while it's not truly a Workload, this helps with generating some of the resources that all workloads also generate
    central_infra_account_name = f"{central_infra_workload_name}-prod"
    central_infra_account = AwsAccount(ou=org_units.central_infra_prod, account_name=central_infra_account_name)

    enable_service_access = (
        Command(  # I think this needs to be after at least 1 other account is created, but maybe not
            "enable-aws-service-access",
            create="aws organizations enable-aws-service-access --service-principal account.amazonaws.com",
            delete="aws organizations disable-aws-service-access --service-principal account.amazonaws.com",
            opts=ResourceOptions(
                depends_on=central_infra_account.wait_after_account_create, delete_before_replace=True
            ),
        )
    )
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/id_root-enable-root-access.html
    enable_iam_service_access = (
        Command(  # I think this needs to be after at least 1 other account is created, but maybe not
            "enable-iam-service-access",
            create="aws organizations enable-aws-service-access --service-principal iam.amazonaws.com",
            delete="aws organizations disable-aws-service-access --service-principal iam.amazonaws.com",
            opts=ResourceOptions(depends_on=enable_service_access, delete_before_replace=True),
        )
    )
    enable_root_creds_management = (
        Command(  # I think this needs to be after at least 1 other account is created, but maybe not
            "enable-root-creds-management",
            create="aws iam enable-organizations-root-credentials-management",
            delete="aws iam disable-organizations-root-credentials-management",
            opts=ResourceOptions(depends_on=enable_iam_service_access, delete_before_replace=True),
        )
    )
    _ = Command(  # I think this needs to be after at least 1 other account is created, but maybe not
        "enable-organizations-root-sessions",
        create="aws iam enable-organizations-root-sessions",
        delete="aws iam disable-organizations-root-sessions",
        opts=ResourceOptions(depends_on=enable_root_creds_management, delete_before_replace=True),
    )
    central_infra_role_arn = central_infra_account.account.id.apply(
        lambda x: f"arn:aws:iam::{x}:role/{DEFAULT_ORG_ACCESS_ROLE_NAME}"
    )
    assume_role = ProviderAssumeRoleArgs(role_arn=central_infra_role_arn, session_name="pulumi")
    central_infra_provider = Provider(
        f"{central_infra_account_name}",
        assume_role=assume_role,
        allowed_account_ids=[central_infra_account.account.id],
        region="us-east-1",
        opts=ResourceOptions(parent=central_infra_account, depends_on=central_infra_account.wait_after_account_create),
    )
    prod_account_data = [account.account_info_kwargs for account in [central_infra_account]]
    all_prod_accounts_resolved = Output.all(
        *[
            Output.all(account["id"], account["name"]).apply(lambda vals: {"id": vals[0], "name": vals[1]})
            for account in prod_account_data
        ]
    )

    def build_central_infra_workload(resolved_prod_accounts: list[dict[str, str]]) -> str:
        # Convert resolved dicts to Pydantic AwsAccountInfo models
        prod_accounts_info = [AwsAccountInfo(**acc) for acc in resolved_prod_accounts]

        logical_workload = AwsLogicalWorkload(
            name=central_infra_workload_name,
            prod_accounts=prod_accounts_info,
        )

        return logical_workload.model_dump_json()

    _ = ssm.Parameter(  # TODO: consider DRY-ing this up with the parameter generation in lib.py
        f"{central_infra_workload_name}-workload-info-for-central-infra",
        type=ssm.ParameterType.STRING,
        description="Hold the logical workload information so that Central Infra account can deploy various resources within them.",
        name=f"{WORKLOAD_INFO_SSM_PARAM_PREFIX}/{central_infra_workload_name}",
        tags=common_tags(),
        value=all_prod_accounts_resolved.apply(build_central_infra_workload),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account, delete_before_replace=True),
    )
    _ = ssm.Parameter(
        f"{central_infra_workload_name}-management-account-id",
        type=ssm.ParameterType.STRING,
        description="The AWS Account ID of the management account",
        name=f"{ORG_MANAGED_SSM_PARAM_PREFIX}/management-account-id",
        tags=common_tags(),
        value=get_aws_account_id(),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account, delete_before_replace=True),
    )

    central_state_bucket = s3.Bucket(
        "central-infra-state",
        tags=common_tags_native(),
        opts=ResourceOptions(
            provider=central_infra_provider,
            parent=central_infra_account,
        ),
    )
    _ = ssm.Parameter(
        "central-infra-state-bucket-name",
        type=ssm.ParameterType.STRING,
        name=f"{ORG_MANAGED_SSM_PARAM_PREFIX}/infra-state-bucket-name",
        tags=common_tags(),
        value=central_state_bucket.bucket_name.apply(lambda x: f"{x}"),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account, delete_before_replace=True),
    )
    kms_key_arn = get_config("proj:kms_key_id")
    assert isinstance(kms_key_arn, str), f"Expected string, got {kms_key_arn} of type {type(kms_key_arn)}"
    _ = ssm.Parameter(
        "central-infra-shared-kms-key-arn",
        type=ssm.ParameterType.STRING,
        name=f"{ORG_MANAGED_SSM_PARAM_PREFIX}/infra-state-kms-key-arn",
        tags=common_tags(),
        value=kms_key_arn,
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account, delete_before_replace=True),
    )

    # TODO: create github OIDC for the central infra repo
    central_infra_prod_github_oidc = iam.OidcProvider(
        "central-infra-repo-github-oidc-provider",
        url="https://token.actions.githubusercontent.com",
        client_id_list=["sts.amazonaws.com"],
        thumbprint_list=["6938fd4d98bab03faadb97b34396831e3780aea1"],  # GitHub's root CA thumbprint
        tags=common_tags_native(),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account),
    )
    preview_assume_role_policy_doc = central_infra_prod_github_oidc.arn.apply(
        lambda oidc_provider_arn: get_policy_document(
            statements=[
                GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        GetPolicyDocumentStatementPrincipalArgs(type="Federated", identifiers=[oidc_provider_arn])
                    ],
                    actions=["sts:AssumeRoleWithWebIdentity"],
                    conditions=[
                        GetPolicyDocumentStatementConditionArgs(
                            test="StringLike",
                            variable="token.actions.githubusercontent.com:sub",
                            values=[f"repo:{CENTRAL_INFRA_GITHUB_ORG_NAME}/{CENTRAL_INFRA_REPO_NAME}:*"],
                        ),
                        GetPolicyDocumentStatementConditionArgs(
                            test="StringEquals",
                            variable="token.actions.githubusercontent.com:aud",
                            values=["sts.amazonaws.com"],
                        ),
                    ],
                )
            ]
        )
    )
    deploy_assume_role_policy_doc = central_infra_prod_github_oidc.arn.apply(
        lambda oidc_provider_arn: get_policy_document(
            statements=[
                GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        GetPolicyDocumentStatementPrincipalArgs(type="Federated", identifiers=[oidc_provider_arn])
                    ],
                    actions=["sts:AssumeRoleWithWebIdentity"],
                    conditions=[
                        GetPolicyDocumentStatementConditionArgs(
                            test="StringEquals",
                            variable="token.actions.githubusercontent.com:sub",
                            values=[
                                f"repo:{CENTRAL_INFRA_GITHUB_ORG_NAME}/{CENTRAL_INFRA_REPO_NAME}:ref:refs/heads/main"
                            ],
                        ),
                        GetPolicyDocumentStatementConditionArgs(
                            test="StringEquals",
                            variable="token.actions.githubusercontent.com:aud",
                            values=["sts.amazonaws.com"],
                        ),
                    ],
                )
            ]
        )
    )

    central_infra_deploy_role = iam.Role(
        "central-infra-repo-deploy",
        role_name=f"InfraDeploy--{CENTRAL_INFRA_REPO_NAME}",
        assume_role_policy_document=deploy_assume_role_policy_doc.json,
        managed_policy_arns=["arn:aws:iam::aws:policy/AdministratorAccess"],
        tags=common_tags_native(),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account),
    )
    deploy_in_workload_account_assume_role_policy = central_infra_deploy_role.arn.apply(
        lambda arn: get_policy_document(
            statements=[
                GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    actions=["sts:AssumeRole"],
                    principals=[GetPolicyDocumentStatementPrincipalArgs(type="AWS", identifiers=[arn])],
                )
            ]
        )
    )

    central_infra_preview_role = iam.Role(
        "central-infra-repo-preview",
        role_name=f"InfraPreview--{CENTRAL_INFRA_REPO_NAME}",
        assume_role_policy_document=preview_assume_role_policy_doc.json,
        managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        policies=[
            create_pulumi_kms_role_policy_args(kms_key_arn),
            iam.RolePolicyArgs(
                policy_document=central_state_bucket.bucket_name.apply(
                    lambda bucket_name: get_policy_document(
                        statements=[
                            GetPolicyDocumentStatementArgs(
                                sid="CreateMetadataAndLocks",
                                effect="Allow",
                                actions=[
                                    "s3:PutObject",
                                ],
                                resources=[f"arn:aws:s3:::{bucket_name}/${{aws:PrincipalAccount}}/*"],
                            ),
                            GetPolicyDocumentStatementArgs(
                                sid="RemoveLock",
                                effect="Allow",
                                actions=[
                                    "s3:DeleteObject",
                                    "s3:DeleteObjectVersion",
                                ],
                                resources=[
                                    f"arn:aws:s3:::{bucket_name}/${{aws:PrincipalAccount}}/*/.pulumi/locks/*.json"
                                ],
                            ),
                            GetPolicyDocumentStatementArgs(
                                sid="ListAllSecrets",
                                effect="Allow",
                                resources=["*"],
                                actions=[
                                    "secretsmanager:ListSecrets",  # when trying to use `secretsmanager:Name` and `secretsmanager:SecretId` to restrict this, it wouldn't let any be listed
                                ],
                            ),
                            GetPolicyDocumentStatementArgs(  # TODO: deprecate and remove this in favor of the more general preview secrets path below
                                sid="ReadGithubPreviewSecret",
                                effect="Allow",
                                actions=[
                                    "secretsmanager:GetSecretValue",
                                ],
                                resources=[
                                    f"arn:aws:secretsmanager:{pulumi_aws.config.region}:*:secret:{GITHUB_PREVIEW_TOKEN_SECRET_NAME}-*"  # TODO: lock down account
                                ],
                            ),
                            GetPolicyDocumentStatementArgs(
                                sid="ReadSecretsForPreviewTokensForIaC",
                                effect="Allow",
                                actions=[
                                    "secretsmanager:GetSecretValue",
                                ],
                                resources=[
                                    f"arn:aws:secretsmanager:{pulumi_aws.config.region}:*:secret:{MANUAL_IAC_SECRETS_PREFIX}/preview-tokens/*"  # TODO: lock down account
                                ],
                            ),
                        ]
                    ).json
                ),
                policy_name="StateBucketWrite",
            ),
            iam.RolePolicyArgs(
                policy_document=get_policy_document(
                    statements=[
                        GetPolicyDocumentStatementArgs(
                            sid="AssumePreviewRolesInOtherAccounts",
                            effect="Allow",
                            actions=["sts:AssumeRole"],
                            resources=[f"arn:aws:iam::*:role/InfraPreview--{CENTRAL_INFRA_REPO_NAME}"],
                        ),
                    ]
                ).json,
                policy_name="AssumePreviewRolesInOtherAccounts",
            ),
        ],
        tags=common_tags_native(),
        opts=ResourceOptions(provider=central_infra_provider, parent=central_infra_account),
    )
    preview_in_workload_account_assume_role_policy = Output.all(
        central_infra_preview_role.arn, central_infra_account.account.account_id
    ).apply(
        lambda args: get_policy_document(
            statements=[
                GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    actions=["sts:AssumeRole"],
                    principals=[
                        GetPolicyDocumentStatementPrincipalArgs(
                            type="AWS",
                            identifiers=[
                                args[0],
                                f"arn:aws:iam::{args[1]}:root",  # TODO: consider locking this further down...but it's just a preview role, and it makes it so users can run previews when working in the central-infra repo
                            ],
                        ),
                    ],
                )
            ]
        )
    )

    return CommonWorkloadKwargs(
        central_infra_account=central_infra_account,
        kms_key_arn=kms_key_arn,
        central_infra_provider=central_infra_provider,
        deploy_in_workload_account_assume_role_policy=deploy_in_workload_account_assume_role_policy,
        preview_in_workload_account_assume_role_policy=preview_in_workload_account_assume_role_policy,
    ), enable_service_access
