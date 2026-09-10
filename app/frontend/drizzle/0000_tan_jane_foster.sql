CREATE TABLE `runtime_snapshots` (
	`owner` text PRIMARY KEY NOT NULL,
	`version` integer NOT NULL,
	`object_key` text NOT NULL,
	`commit_id` text NOT NULL,
	`digest` text NOT NULL,
	`updated_at` integer NOT NULL
);
