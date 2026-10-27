-- Generated schema reference v1. Application bootstrap uses SQLAlchemy metadata.
-- Do not apply over an existing live database without a reviewed migration.


CREATE TABLE auth_attempts (
	id VARCHAR(36) NOT NULL, 
	key VARCHAR(80) NOT NULL, 
	at INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_auth_attempts_at ON auth_attempts (at);

CREATE INDEX ix_auth_attempts_key ON auth_attempts (key);


CREATE TABLE leases (
	key VARCHAR(220) NOT NULL, 
	owner VARCHAR(64) NOT NULL, 
	expires_at INTEGER NOT NULL, 
	PRIMARY KEY (key)
)

;


CREATE TABLE organizations (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	emergency_stop BOOLEAN NOT NULL, 
	demo BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

;


CREATE TABLE schema_versions (
	version SERIAL NOT NULL, 
	applied_at INTEGER NOT NULL, 
	PRIMARY KEY (version)
)

;


CREATE TABLE system (
	key VARCHAR(80) NOT NULL, 
	value JSON NOT NULL, 
	PRIMARY KEY (key)
)

;


CREATE TABLE connections (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	credential TEXT NOT NULL, 
	scope TEXT NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_connections_org_id ON connections (org_id);


CREATE TABLE invitations (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	role VARCHAR(30) NOT NULL, 
	stores JSON NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at INTEGER NOT NULL, 
	used_at INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	UNIQUE (token_hash)
)

;


CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	role VARCHAR(30) NOT NULL, 
	password_hash TEXT NOT NULL, 
	active BOOLEAN NOT NULL, 
	mfa_secret TEXT, 
	pending_mfa TEXT, 
	mfa_counter INTEGER NOT NULL, 
	recovery_codes JSON NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	UNIQUE (email)
)

;

CREATE INDEX ix_users_org_id ON users (org_id);


CREATE TABLE recovery_codes (
	user_id VARCHAR(36) NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	used_at INTEGER, 
	PRIMARY KEY (user_id, code_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE sessions (
	id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	csrf VARCHAR(80) NOT NULL, 
	created_at INTEGER NOT NULL, 
	expires_at INTEGER NOT NULL, 
	last_seen INTEGER NOT NULL, 
	stepup_until INTEGER NOT NULL, 
	mfa_verified BOOLEAN NOT NULL, 
	user_agent VARCHAR(200) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_sessions_user_id ON sessions (user_id);


CREATE TABLE stores (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	marketplace VARCHAR(30) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	timezone VARCHAR(80) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	connection_id VARCHAR(36), 
	spreadsheet_id VARCHAR(180), 
	sheet_id INTEGER, 
	tab_name VARCHAR(150), 
	header_row INTEGER NOT NULL, 
	mapping JSON NOT NULL, 
	mapping_version INTEGER NOT NULL, 
	financial_approved BOOLEAN NOT NULL, 
	financial_basis VARCHAR(30) NOT NULL, 
	include_filler BOOLEAN NOT NULL, 
	writes_enabled BOOLEAN NOT NULL, 
	writer_contract BOOLEAN NOT NULL, 
	gates JSON NOT NULL, 
	poll_seconds INTEGER NOT NULL, 
	next_sync INTEGER NOT NULL, 
	last_sync INTEGER, 
	sync_error TEXT, 
	max_rows INTEGER NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(connection_id) REFERENCES connections (id)
)

;

CREATE INDEX ix_stores_next_sync ON stores (next_sync);

CREATE INDEX ix_stores_org_id ON stores (org_id);


CREATE TABLE assignments (
	user_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (user_id, store_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;


CREATE TABLE audit (
	seq SERIAL NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36), 
	actor_id VARCHAR(36), 
	action VARCHAR(100) NOT NULL, 
	object_id VARCHAR(100), 
	details JSON NOT NULL, 
	at INTEGER NOT NULL, 
	PRIMARY KEY (seq), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_audit_org_id ON audit (org_id);


CREATE TABLE financial_entries (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	amount NUMERIC(22, 4) NOT NULL, 
	recognized_on VARCHAR(10) NOT NULL, 
	reason TEXT NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (store_id, idempotency_key), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_financial_entries_store_id ON financial_entries (store_id);


CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36), 
	kind VARCHAR(20) NOT NULL, 
	payload JSON NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	attempts INTEGER NOT NULL, 
	available_at INTEGER NOT NULL, 
	started_at INTEGER, 
	finished_at INTEGER, 
	error TEXT, 
	result JSON NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_jobs_available_at ON jobs (available_at);

CREATE INDEX ix_jobs_org_id ON jobs (org_id);

CREATE INDEX ix_jobs_state ON jobs (state);


CREATE TABLE milestones (
	id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	level INTEGER NOT NULL, 
	target_version INTEGER NOT NULL, 
	muted BOOLEAN NOT NULL, 
	at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (store_id, month, level), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_milestones_store_id ON milestones (store_id);


CREATE TABLE notifications (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36), 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	financial BOOLEAN NOT NULL, 
	dedupe_key VARCHAR(200) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (org_id, dedupe_key), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_notifications_org_id ON notifications (org_id);


CREATE TABLE oauth_states (
	state_hash VARCHAR(64) NOT NULL, 
	session_id VARCHAR(64) NOT NULL, 
	verifier TEXT NOT NULL, 
	expires_at INTEGER NOT NULL, 
	PRIMARY KEY (state_hash), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE
)

;


CREATE TABLE orders (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	ebay_id VARCHAR(100) NOT NULL, 
	sold_on VARCHAR(10) NOT NULL, 
	title TEXT NOT NULL, 
	earnings NUMERIC(22, 4), 
	cost NUMERIC(22, 4), 
	extra NUMERIC(22, 4) NOT NULL, 
	refund NUMERIC(22, 4) NOT NULL, 
	credit NUMERIC(22, 4) NOT NULL, 
	filler NUMERIC(22, 4) NOT NULL, 
	supplier_ref VARCHAR(150) NOT NULL, 
	tracking VARCHAR(200) NOT NULL, 
	courier VARCHAR(100) NOT NULL, 
	postcode VARCHAR(30) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	notes TEXT NOT NULL, 
	origin VARCHAR(20) NOT NULL, 
	source_row INTEGER, 
	source_values JSON NOT NULL, 
	issues JSON NOT NULL, 
	observed BOOLEAN NOT NULL, 
	revision INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_order_store_ebay UNIQUE (store_id, ebay_id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_order_store_date ON orders (store_id, sold_on);

CREATE INDEX ix_orders_org_id ON orders (org_id);

CREATE INDEX ix_orders_store_id ON orders (store_id);


CREATE TABLE period_closes (
	store_id VARCHAR(36) NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	snapshot JSON NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (store_id, month), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE targets (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	amount NUMERIC(22, 4) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (store_id, month), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

;

CREATE INDEX ix_targets_store_id ON targets (store_id);


CREATE TABLE tasks (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	assignee_id VARCHAR(36), 
	due_on VARCHAR(10), 
	status VARCHAR(20) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(assignee_id) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;

CREATE INDEX ix_tasks_org_id ON tasks (org_id);


CREATE TABLE celebration_seen (
	user_id VARCHAR(36) NOT NULL, 
	notification_id VARCHAR(36) NOT NULL, 
	at INTEGER NOT NULL, 
	PRIMARY KEY (user_id, notification_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id)
)

;


CREATE TABLE notification_reads (
	user_id VARCHAR(36) NOT NULL, 
	notification_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (user_id, notification_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id)
)

;


CREATE TABLE write_intents (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	store_id VARCHAR(36) NOT NULL, 
	order_id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	approver_id VARCHAR(36), 
	base JSON NOT NULL, 
	proposed JSON NOT NULL, 
	postcode VARCHAR(30) NOT NULL, 
	mapping_version INTEGER NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	reason TEXT NOT NULL, 
	error TEXT, 
	idempotency_key VARCHAR(100) NOT NULL, 
	created_at INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (org_id, idempotency_key), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(approver_id) REFERENCES users (id)
)

;

CREATE INDEX ix_write_intents_org_id ON write_intents (org_id);

CREATE INDEX ix_write_intents_state ON write_intents (state);
