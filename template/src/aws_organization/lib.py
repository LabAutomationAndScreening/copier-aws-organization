from pydantic import BaseModel
from pydantic import Field


class AwsAccountInfo(BaseModel, frozen=True):
    account_id: str
    account_name: str


class AwsLogicalWorkload(BaseModel, frozen=True):
    name: str
    production_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    staging_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    development_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs


class AwsLogicalWorkloads(BaseModel, frozen=True):
    logical_workloads: list[AwsLogicalWorkload]
