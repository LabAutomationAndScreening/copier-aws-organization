from pydantic import BaseModel
from pydantic import Field


class AwsAccountInfo(BaseModel, frozen=True):
    version: str = "0.0.1"
    id: str
    name: str


class AwsLogicalWorkload(BaseModel):
    version: str = "0.0.1"
    name: str
    prod_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    staging_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
    dev_accounts: list[AwsAccountInfo] = Field(
        default_factory=list
    )  # TODO: convert to a set with deterministic ordering to avoid false positive diffs
