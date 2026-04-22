from __future__ import annotations

import logging
import sys

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import IO, Any

import boto3

from botocore.exceptions import ClientError

from cirrus.lib.payload_bucket import PayloadBucket
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import get_client, get_resource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DbUpdatePlan:
    """Pure-data description of a DynamoDB update for a single record."""

    key: dict[str, str]
    set_parts: tuple[str, ...]
    remove_parts: tuple[str, ...]
    attr_values: dict[str, Any]

    @property
    def expression(self) -> str:
        parts: list[str] = []
        if self.set_parts:
            parts.append("SET " + ", ".join(self.set_parts))
        if self.remove_parts:
            parts.append("REMOVE " + ", ".join(self.remove_parts))
        return " ".join(parts)

    def is_noop(self) -> bool:
        return not self.set_parts and not self.remove_parts

    def to_update_item_kwargs(self) -> dict[str, Any]:
        """Build the kwargs dict for a boto3 Table.update_item call."""
        kwargs: dict[str, Any] = {
            "Key": self.key,
            "UpdateExpression": self.expression,
        }
        if self.attr_values:
            kwargs["ExpressionAttributeValues"] = self.attr_values
        return kwargs


class MigrationRecord:
    """Thin, immutable view over a DynamoDB record for migration purposes."""

    def __init__(self, item: dict) -> None:
        self.item = item

    @property
    def key(self) -> dict[str, str]:
        return {
            "collections_workflow": self.item["collections_workflow"],
            "itemids": self.item["itemids"],
        }

    @property
    def payload_id(self) -> str:
        return StateDB.key_to_payload_id(self.key)

    @property
    def state_updated(self) -> str:
        return self.item.get("state_updated", "")

    @property
    def state_timestamp(self) -> str:
        su = self.state_updated
        return su.split("_", 1)[1] if "_" in su else ""

    @property
    def original_state(self) -> str:
        return self.state_updated.split("_")[0]

    @property
    def executions(self) -> list[str]:
        return self.item.get("executions", [])

    @property
    def last_execution_arn(self) -> str | None:
        return self.executions[-1] if self.executions else None

    @property
    def execution_id(self) -> str | None:
        arn = self.last_execution_arn
        return StateDB.execution_id_from_arn(arn) if arn else None

    @property
    def updated_dt(self) -> datetime | None:
        updated = self.item.get("updated")
        if updated is None:
            return None
        try:
            dt = datetime.fromisoformat(str(updated))
        except (ValueError, TypeError):
            return None
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt

    @property
    def already_migrated(self) -> bool:
        return "claimed_at" in self.item

    def build_db_update_plan(self) -> DbUpdatePlan:
        """Build a data-only plan describing the DynamoDB mutation for this record."""
        set_parts: list[str] = []
        remove_parts: list[str] = []
        attr_values: dict[str, Any] = {}

        # Rename COMPLETED -> SUCCEEDED
        if self.original_state == "COMPLETED":
            ts = self.state_timestamp
            set_parts.append("state_updated = :su")
            attr_values[":su"] = f"SUCCEEDED_{ts}" if ts else "SUCCEEDED"

        # Set claimed_at from created
        if "created" in self.item and "claimed_at" not in self.item:
            set_parts.append("claimed_at = :ca")
            attr_values[":ca"] = self.item["created"]

        # Remove last_error from non-FAILED records
        if self.original_state != "FAILED" and "last_error" in self.item:
            remove_parts.append("last_error")

        # Remove outputs from non-SUCCEEDED records
        if "outputs" in self.item and self.original_state not in (
            "SUCCEEDED",
            "COMPLETED",
        ):
            remove_parts.append("outputs")

        return DbUpdatePlan(
            key=self.key,
            set_parts=tuple(set_parts),
            remove_parts=tuple(remove_parts),
            attr_values=attr_values,
        )


class Migrator:
    """Runs the state DB / payload bucket migration for a deployment."""

    def __init__(
        self,
        session: boto3.Session,
        table_name: str,
        bucket_name: str,
        root_prefix: str | None = None,
        since_days: int = 90,
        dry_run: bool = False,
        output: IO = sys.stderr,
    ) -> None:
        dynamodb = get_resource("dynamodb", session=session)
        self.table = dynamodb.Table(table_name)  # type: ignore
        self.s3 = get_client("s3", session=session)
        self.sfn = get_client("stepfunctions", session=session)
        self.payload_bucket = PayloadBucket(bucket_name, root_prefix=root_prefix)
        self.bucket_name = bucket_name
        self.cutoff = datetime.now(UTC) - timedelta(days=since_days)
        self.dry_run = dry_run
        self.output = output
        self.counts = {
            "processed": 0,
            "db_updated": 0,
            "s3_copied": 0,
            "s3_output_uploaded": 0,
            "skipped": 0,
            "db_errors": 0,
            "s3_copy_errors": 0,
            "sfn_output_errors": 0,
            "unexpected_errors": 0,
        }

    def run(self) -> None:
        scan_kwargs: dict[str, Any] = {}
        while True:
            response = self.table.scan(**scan_kwargs)
            items = response.get("Items", [])

            for item in items:
                self.counts["processed"] += 1
                try:
                    self.migrate_record(MigrationRecord(item))
                except Exception:
                    self.counts["unexpected_errors"] += 1
                    logger.exception(
                        "Unexpected error migrating record %s/%s",
                        item.get("collections_workflow"),
                        item.get("itemids"),
                    )

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key

        self.output.write(
            f"\nMigration {'(dry run) ' if self.dry_run else ''}complete.\n"
            f"  Records processed:   {self.counts['processed']}\n"
            f"  DB updated:          {self.counts['db_updated']}\n"
            f"  S3 input copied:     {self.counts['s3_copied']}\n"
            f"  S3 output uploaded:  {self.counts['s3_output_uploaded']}\n"
            f"  Skipped:             {self.counts['skipped']}\n"
            f"  DB errors:           {self.counts['db_errors']}\n"
            f"  S3 copy errors:      {self.counts['s3_copy_errors']}\n"
            f"  SFN output errors:   {self.counts['sfn_output_errors']}\n"
            f"  Unexpected errors:   {self.counts['unexpected_errors']}\n",
        )

    def migrate_record(self, rec: MigrationRecord) -> None:
        if rec.already_migrated:
            return

        # copy input payload BEFORE updating record so a partial
        # failure leaves claimed_at unset and a re-run can finish
        self.copy_input_payload(rec)

        # fetch SFN output for legacy COMPLETED+recent records and upload to S3
        self.copy_output_payload(rec)

        # statedb update last and marks that migration is complete
        self.update_db_record(rec)

    def update_db_record(self, rec: MigrationRecord) -> bool:
        """StateDB update. Returns True on success (or no-op), False on failure."""
        plan = rec.build_db_update_plan()
        if plan.is_noop():
            return True

        if self.dry_run:
            self.output.write(
                f"[DRY RUN] Would update {rec.payload_id}: {plan.expression}\n",
            )
            self.counts["db_updated"] += 1
            return True

        try:
            self.table.update_item(**plan.to_update_item_kwargs())
        except ClientError:
            self.counts["db_errors"] += 1
            logger.exception(
                "DynamoDB update failed for %s (expression: %s)",
                rec.payload_id,
                plan.expression,
            )
            return False

        self.counts["db_updated"] += 1
        return True

    def copy_input_payload(self, rec: MigrationRecord) -> None:
        """Step B: S3 input payload copy."""
        if not rec.execution_id:
            return

        old_key = f"{rec.payload_id}/input.json"
        _, new_key = PayloadBucket.parse_url(
            self.payload_bucket.get_input_payload_url(
                rec.payload_id,
                rec.execution_id,
            ),
        )

        if self.dry_run:
            self.output.write(
                f"[DRY RUN] Would copy s3://{self.bucket_name}/{old_key}"
                f" -> s3://{self.bucket_name}/{new_key}\n",
            )
            self.counts["s3_copied"] += 1
            return

        try:
            self.s3.copy_object(
                Bucket=self.bucket_name,
                CopySource={"Bucket": self.bucket_name, "Key": old_key},
                Key=new_key,
            )
            self.counts["s3_copied"] += 1
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                self.counts["skipped"] += 1
                logger.debug(
                    "No existing input payload at %s, skipping copy",
                    old_key,
                )
            else:
                self.counts["s3_copy_errors"] += 1
                logger.exception(
                    "S3 copy failed for %s -> %s",
                    old_key,
                    new_key,
                )

    def copy_output_payload(self, rec: MigrationRecord) -> None:
        """Step C: S3 output payload from SFN."""
        if not (
            # SUCCEEDED outputs do not need to be migrated
            rec.original_state == "COMPLETED"
            and rec.updated_dt is not None
            and rec.updated_dt >= self.cutoff
        ):
            return

        if not (rec.last_execution_arn and rec.execution_id):
            return

        last_arn = rec.last_execution_arn
        _, output_key = PayloadBucket.parse_url(
            self.payload_bucket.get_output_payload_url(
                rec.payload_id,
                rec.execution_id,
            ),
        )

        if self.dry_run:
            self.output.write(
                f"[DRY RUN] Would fetch SFN output for {last_arn}"
                f" -> s3://{self.bucket_name}/{output_key}\n",
            )
            self.counts["s3_output_uploaded"] += 1
            return

        try:
            execution = self.sfn.describe_execution(executionArn=last_arn)
            sfn_output = execution.get("output")
            if sfn_output:
                self.s3.put_object(
                    Bucket=self.bucket_name,
                    Key=output_key,
                    Body=sfn_output.encode(),
                    ContentType="application/json",
                )
                self.counts["s3_output_uploaded"] += 1
            else:
                self.counts["skipped"] += 1
                logger.debug(
                    "No output in SFN execution %s",
                    last_arn,
                )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ExecutionDoesNotExist":
                self.counts["skipped"] += 1
                logger.debug(
                    "SFN execution %s no longer exists (past retention)",
                    last_arn,
                )
            else:
                self.counts["sfn_output_errors"] += 1
                logger.exception(
                    "SFN output fetch failed for %s -> s3://%s/%s",
                    last_arn,
                    self.bucket_name,
                    output_key,
                )
        except self.sfn.exceptions.ExecutionDoesNotExist:
            self.counts["skipped"] += 1
            logger.debug(
                "SFN execution %s no longer exists (past retention)",
                last_arn,
            )
