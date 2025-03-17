import logging

from ephemeral_pulumi_deploy import get_aws_account_id
from ephemeral_pulumi_deploy import get_config
from pulumi import ResourceOptions
from pulumi import export
from pulumi_aws.organizations import DelegatedAdministrator
from pulumi_aws.organizations import DelegatedAdministratorArgs
from pulumi_command.local import Command

from ..workloads import create_workloads
from .central_infra_workload import create_central_infra_workload
from .constants import CONFIGURE_CLOUD_COURIER
from .org_units import create_organizational_units
from .workload import AwsWorkload

logger = logging.getLogger(__name__)


def pulumi_program() -> None:
    """Execute creating the stack."""
    aws_account_id = get_aws_account_id()
    export("aws-account-id", aws_account_id)
    env = get_config("proj:env")
    export("env", env)

    # Create Resources Here
    org_units = create_organizational_units()

    common_workload_kwargs, enable_service_access = create_central_infra_workload(org_units)
    identity_center_delegate_workload = AwsWorkload(
        workload_name="identity-center",
        prod_ou=org_units.central_infra_prod,
        prod_account_name_suffixes=["prod"],
        **common_workload_kwargs,
    )
    _ = DelegatedAdministrator(
        "delegate-admin-to-identity-center-prod",
        DelegatedAdministratorArgs(
            account_id=identity_center_delegate_workload.prod_accounts[0].account.id,
            service_principal="sso.amazonaws.com",
        ),
        opts=ResourceOptions(
            parent=identity_center_delegate_workload.prod_accounts[0],
            depends_on=[
                identity_center_delegate_workload.prod_accounts[0].wait_after_account_create,
                enable_service_access,
            ],
        ),
    )
    billing_delegate_workload = AwsWorkload(
        workload_name="billing-delegate",
        prod_ou=org_units.central_infra_prod,
        prod_account_name_suffixes=["prod"],
        **common_workload_kwargs,
    )
    enable_billing_service_access = Command(  # I think this needs to be after at least 1 other account is created, but maybe not
        "enable-aws-service-access-for-billing",
        create="aws organizations enable-aws-service-access --service-principal cost-optimization-hub.bcm.amazonaws.com",
        opts=ResourceOptions(depends_on=billing_delegate_workload.prod_accounts[0].wait_after_account_create),
    )
    _ = DelegatedAdministrator(
        "delegate-billing-admin",
        DelegatedAdministratorArgs(
            account_id=billing_delegate_workload.prod_accounts[0].account.id,
            service_principal="cost-optimization-hub.bcm.amazonaws.com",
        ),
        opts=ResourceOptions(
            parent=billing_delegate_workload.prod_accounts[0],
            depends_on=[
                billing_delegate_workload.prod_accounts[0].wait_after_account_create,
                enable_billing_service_access,
            ],
        ),
    )
    create_workloads(org_units=org_units, common_workload_kwargs=common_workload_kwargs)
    if CONFIGURE_CLOUD_COURIER:
        _ = AwsWorkload(
            workload_name="cloud-courier",
            prod_ou=org_units.non_qualified_workload_prod,
            prod_account_name_suffixes=["production"],
            dev_account_name_suffixes=["development"],
            staging_account_name_suffixes=["staging"],
            dev_ou=org_units.non_qualified_workload_dev,
            staging_ou=org_units.non_qualified_workload_staging,
            **common_workload_kwargs,
        )
