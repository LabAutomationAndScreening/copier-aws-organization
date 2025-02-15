from ephemeral_pulumi_deploy.utils import common_tags_native
from pulumi import ResourceOptions
from pulumi_aws.organizations import get_organization
from pulumi_aws_native import organizations
from pulumi_aws_native.organizations import OrganizationalUnit
from pydantic import BaseModel
from pydantic import ConfigDict


class OrganizationalUnits(BaseModel):
    central_infra: OrganizationalUnit
    central_infra_prod: OrganizationalUnit
    non_qualified_workload: OrganizationalUnit
    non_qualified_workload_prod: OrganizationalUnit
    non_qualified_workload_staging: OrganizationalUnit
    non_qualified_workload_dev: OrganizationalUnit
    model_config = ConfigDict(arbitrary_types_allowed=True)


def create_organizational_units() -> OrganizationalUnits:
    organization_root_id = get_organization().roots[0].id

    central_infra_ou = organizations.OrganizationalUnit(
        "CentralizedInfrastructure",
        name="CentralizedInfrastructure",
        parent_id=organization_root_id,
        tags=common_tags_native(),
    )
    central_infra_prod_ou = organizations.OrganizationalUnit(
        "CentralInfraProd",
        name="Prod",
        parent_id=central_infra_ou.id,
        tags=common_tags_native(),
        opts=ResourceOptions(parent=central_infra_ou, delete_before_replace=True),
    )

    non_qualified_workload_ou = organizations.OrganizationalUnit(
        "NonQualifiedWorkloads",
        name="NonQualifiedWorkloads",
        parent_id=organization_root_id,
        tags=common_tags_native(),
    )
    workload_prod_ou = organizations.OrganizationalUnit(
        "NonQualifiedWorkloadProd",
        name="Prod",
        parent_id=non_qualified_workload_ou.id,
        tags=common_tags_native(),
        opts=ResourceOptions(parent=non_qualified_workload_ou, delete_before_replace=True),
    )
    workload_dev_ou = organizations.OrganizationalUnit(
        "NonQualifiedWorkloadDev",
        name="Dev",
        parent_id=non_qualified_workload_ou.id,
        tags=common_tags_native(),
        opts=ResourceOptions(parent=non_qualified_workload_ou, delete_before_replace=True),
    )
    workload_staging_ou = organizations.OrganizationalUnit(
        "NonQualifiedWorkloadStaging",
        name="Staging",
        parent_id=non_qualified_workload_ou.id,
        tags=common_tags_native(),
        opts=ResourceOptions(parent=non_qualified_workload_ou, delete_before_replace=True),
    )
    return OrganizationalUnits(
        central_infra=central_infra_ou,
        central_infra_prod=central_infra_prod_ou,
        non_qualified_workload=non_qualified_workload_ou,
        non_qualified_workload_prod=workload_prod_ou,
        non_qualified_workload_staging=workload_staging_ou,
        non_qualified_workload_dev=workload_dev_ou,
    )
