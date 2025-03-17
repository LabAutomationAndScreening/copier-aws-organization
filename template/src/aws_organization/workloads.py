from .lib import AwsWorkload
from .lib import CommonWorkloadKwargs
from .lib import OrganizationalUnits


def create_workloads(
    *, org_units: OrganizationalUnits, common_workload_kwargs: CommonWorkloadKwargs, workloads: list[AwsWorkload]
) -> None:
    """Define workloads.

    Example:
    ```
    workloads.append(
        AwsWorkload(
            workload_name="green-button-go",
            prod_ou=org_units.non_qualified_workload_prod,
            prod_account_name_suffixes=["production"],
            staging_account_name_suffixes=["staging"],
            dev_account_name_suffixes=["development"],
            dev_ou=org_units.non_qualified_workload_dev,
            staging_ou=org_units.non_qualified_workload_staging,
            **common_workload_kwargs,
        )
    )
    ```
    """
