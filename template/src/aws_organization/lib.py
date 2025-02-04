from pydantic import BaseModel


class AwsAccountInfo(BaseModel, frozen=True):
    account_id: str
    account_name: str


class AwsLogicalWorkload(BaseModel, frozen=True):
    logical_workload_name: str
    production_accounts: list[
        AwsAccountInfo
    ]  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    staging_accounts: list[
        AwsAccountInfo
    ]  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    development_accounts: list[
        AwsAccountInfo
    ]  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
