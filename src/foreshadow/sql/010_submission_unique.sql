-- One Gate-2 snapshot owns one durable submission record.
CREATE UNIQUE INDEX idx_submissions_snapshot_unique
ON submissions(approval_snapshot_id);
