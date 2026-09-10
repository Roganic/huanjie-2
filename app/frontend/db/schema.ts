import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
export const runtimeSnapshots = sqliteTable('runtime_snapshots', {
  owner: text('owner').primaryKey(),
  version: integer('version').notNull(),
  objectKey: text('object_key').notNull(),
  commitId: text('commit_id').notNull(),
  digest: text('digest').notNull(),
  updatedAt: integer('updated_at').notNull(),
});

export const modelUsage = sqliteTable('model_usage', {
  id: text('id').primaryKey(),
  model: text('model').notNull(),
  createdAt: integer('created_at').notNull(),
  reserved: integer('reserved').notNull(),
  charged: integer('charged').notNull(),
  state: text('state').notNull(),
  inputTokens: integer('input_tokens'),
  outputTokens: integer('output_tokens'),
});
