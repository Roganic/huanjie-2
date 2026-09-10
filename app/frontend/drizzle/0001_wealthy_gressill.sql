CREATE TABLE `model_usage` (
	`id` text PRIMARY KEY NOT NULL,
	`model` text NOT NULL,
	`created_at` integer NOT NULL,
	`reserved` integer NOT NULL,
	`charged` integer NOT NULL,
	`state` text NOT NULL,
	`input_tokens` integer,
	`output_tokens` integer
);
