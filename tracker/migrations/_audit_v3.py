"""Frozen trigger definitions for migration 0005 (do not change after deployment)."""
import uuid

# Explicit safe field allowlists: no passwords, hashes, secrets, or push endpoints.
SPECS = {
    'tracker_bill': ('bill', 'title', ['id', 'title', 'amount', 'due_date', 'category', 'notes', 'responsible_id', 'created_by_id', 'loan_id', 'recurrence_id', 'removed']),
    'tracker_payment': ('payment', None, ['id', 'bill_id', 'amount', 'paid_date', 'recorded_by_id', 'removed']),
    'tracker_loan': ('loan', 'title', ['id', 'title', 'total', 'installments', 'created_by_id', 'removed']),
    'tracker_recurrence': ('recurrence', 'title', ['id', 'title', 'amount', 'category', 'next_due', 'anchor_day', 'responsible_id', 'created_by_id', 'active', 'removed']),
    'tracker_sitesettings': ('settings', None, ['id', 'family_name', 'nas_name', 'server_url']),
    'auth_user': ('account', 'username', ['id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser']),
    'auth_user_groups': ('access', None, ['id', 'user_id', 'group_id']),
    'auth_user_user_permissions': ('access', None, ['id', 'user_id', 'permission_id']),
    'auth_group': ('access', 'name', ['id', 'name']),
    'auth_group_permissions': ('access', None, ['id', 'group_id', 'permission_id']),
    'tracker_pushsubscription': ('device', None, ['id', 'user_id']),
    'tracker_reminderdelivery': ('reminder', None, ['id', 'bill_id', 'subscription_id', 'day', 'delivered_at', 'attempts']),
}


def snapshot(prefix, fields, vendor):
    pairs = []
    for field in fields:
        expression = f'{prefix}."{field}"'
        if vendor == 'sqlite' and field in ('removed','active','is_active','is_staff','is_superuser'):
            expression = f"json(CASE WHEN {expression} THEN 'true' ELSE 'false' END)"
        if field in ('amount', 'total'):
            expression = f'CAST({expression} AS TEXT)'
        pairs.extend([f"'{field}'", expression])
    function = 'jsonb_build_object' if vendor == 'postgresql' else 'json_object'
    return f'{function}({", ".join(pairs)})'


def install(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    Context = apps.get_model('tracker', 'AuditContext')
    Context.objects.using(schema_editor.connection.alias).get_or_create(pk=1)
    for table, (kind, label_field, fields) in SPECS.items():
        comparisons = [f'OLD."{f}" IS DISTINCT FROM NEW."{f}"' if vendor == 'postgresql' else f'OLD."{f}" IS NOT NEW."{f}"' for f in fields]
        if table == 'auth_user':
            comparisons.append('OLD.password IS DISTINCT FROM NEW.password' if vendor == 'postgresql' else 'OLD.password IS NOT NEW.password')
        changed = ' OR '.join(comparisons)
        for action, ref in [('insert', 'NEW'), ('update', 'NEW'), ('delete', 'OLD')]:
            before = 'NULL' if action == 'insert' else snapshot('OLD', fields, vendor)
            after = 'NULL' if action == 'delete' else snapshot('NEW', fields, vendor)
            label = f'CAST({ref}."{label_field}" AS TEXT)' if label_field else f"'{kind.capitalize()} #' || CAST({ref}.id AS TEXT)"
            credential_change = ('(OLD.password IS DISTINCT FROM NEW.password)' if vendor == 'postgresql' else '(OLD.password IS NOT NEW.password)') if table == 'auth_user' and action == 'update' else ('FALSE' if vendor == 'postgresql' else '0')
            trigger = f'fbt_audit_{table}_{action}'
            columns = 'occurred_at, actor_id, actor_name, transaction_id, source, reason, action, entity_type, entity_id, entity_table, label, "before", "after", credentials_changed'
            if vendor == 'postgresql':
                statement = f'''CREATE FUNCTION {trigger}_fn() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    INSERT INTO tracker_auditevent ({columns}) VALUES (
                        clock_timestamp(), NULLIF(current_setting('fbt.audit_actor_id', true), '')::bigint,
                        COALESCE(NULLIF(current_setting('fbt.audit_actor_name', true), ''), 'Database / unknown actor'),
                        COALESCE(NULLIF(current_setting('fbt.audit_transaction_id', true), ''), 'db:' || txid_current()::text),
                        COALESCE(NULLIF(current_setting('fbt.audit_source', true), ''), 'database'),
                        COALESCE(current_setting('fbt.audit_reason', true), ''),
                        '{action}', '{kind}', CAST({ref}.id AS TEXT), '{table}', LEFT({label}, 180), {before}, {after}, {credential_change});
                    RETURN {ref};
                END; $$'''
                schema_editor.execute(statement)
                when = f' WHEN ({changed})' if action == 'update' else ''
                schema_editor.execute(f'CREATE TRIGGER {trigger} AFTER {action.upper()} ON "{table}" FOR EACH ROW{when} EXECUTE FUNCTION {trigger}_fn()')
            elif vendor == 'sqlite':
                when = f' WHEN {changed}' if action == 'update' else ''
                schema_editor.execute(f'''CREATE TRIGGER {trigger} AFTER {action.upper()} ON "{table}"{when}
                BEGIN
                    INSERT INTO tracker_auditevent ({columns}) VALUES (
                        STRFTIME('%Y-%m-%d %H:%M:%f', 'now'),
                        (SELECT actor_id FROM tracker_auditcontext WHERE id=1),
                        COALESCE(NULLIF((SELECT actor_name FROM tracker_auditcontext WHERE id=1), ''), 'Database / unknown actor'),
                        COALESCE(NULLIF((SELECT transaction_id FROM tracker_auditcontext WHERE id=1), ''), LOWER(HEX(RANDOMBLOB(16)))),
                        COALESCE(NULLIF((SELECT source FROM tracker_auditcontext WHERE id=1), ''), 'database'),
                        COALESCE((SELECT reason FROM tracker_auditcontext WHERE id=1), ''),
                        '{action}', '{kind}', CAST({ref}.id AS TEXT), '{table}', SUBSTR({label}, 1, 180), {before}, {after}, {credential_change});
                END''')
            else:
                raise RuntimeError('Audit triggers support PostgreSQL and SQLite only.')

    # Balance protection also applies to raw SQL and updates outside the HTTP API.
    if vendor == 'postgresql':
        schema_editor.execute('''CREATE FUNCTION fbt_payment_balance_fn() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE limit_amount numeric; paid numeric;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                PERFORM id FROM tracker_bill WHERE id IN (OLD.bill_id, NEW.bill_id) ORDER BY id FOR UPDATE;
            END IF;
            SELECT amount INTO limit_amount FROM tracker_bill WHERE id = NEW.bill_id FOR UPDATE;
            SELECT COALESCE(SUM(amount), 0) INTO paid FROM tracker_payment WHERE bill_id = NEW.bill_id AND NOT removed AND id <> CASE WHEN TG_OP = 'UPDATE' THEN OLD.id ELSE NEW.id END;
            IF NOT NEW.removed AND paid + NEW.amount > limit_amount THEN RAISE EXCEPTION 'Payment exceeds unpaid balance' USING ERRCODE = '23514'; END IF;
            RETURN NEW;
        END; $$''')
        schema_editor.execute('CREATE TRIGGER fbt_payment_balance BEFORE INSERT OR UPDATE ON tracker_payment FOR EACH ROW EXECUTE FUNCTION fbt_payment_balance_fn()')
        schema_editor.execute('''CREATE FUNCTION fbt_bill_balance_fn() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.amount < (SELECT COALESCE(SUM(amount), 0) FROM tracker_payment WHERE bill_id=NEW.id AND NOT removed) THEN
                RAISE EXCEPTION 'Bill amount cannot be less than recorded payments' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$''')
        schema_editor.execute('CREATE TRIGGER fbt_bill_balance BEFORE UPDATE OF amount ON tracker_bill FOR EACH ROW EXECUTE FUNCTION fbt_bill_balance_fn()')
    else:
        for action in ('INSERT', 'UPDATE'):
            excluded = 'OLD.id' if action == 'UPDATE' else 'NEW.id'
            schema_editor.execute(f'''CREATE TRIGGER fbt_payment_balance_{action.lower()} BEFORE {action} ON tracker_payment
            WHEN NOT NEW.removed AND NEW.amount + (SELECT COALESCE(SUM(amount), 0) FROM tracker_payment WHERE bill_id=NEW.bill_id AND NOT removed AND id <> {excluded}) > (SELECT amount FROM tracker_bill WHERE id=NEW.bill_id)
            BEGIN SELECT RAISE(ABORT, 'Payment exceeds unpaid balance'); END''')
        schema_editor.execute('''CREATE TRIGGER fbt_bill_balance BEFORE UPDATE OF amount ON tracker_bill
        WHEN NEW.amount < (SELECT COALESCE(SUM(amount), 0) FROM tracker_payment WHERE bill_id=NEW.id AND NOT removed)
        BEGIN SELECT RAISE(ABORT, 'Bill amount cannot be less than recorded payments'); END''')



def uninstall(apps, schema_editor):
    postgres = schema_editor.connection.vendor == 'postgresql'
    for table in SPECS:
        for action in ('insert', 'update', 'delete'):
            trigger = f'fbt_audit_{table}_{action}'
            suffix = f' ON "{table}"' if postgres else ''
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {trigger}{suffix}')
            if postgres:
                schema_editor.execute(f'DROP FUNCTION IF EXISTS {trigger}_fn()')
    if postgres:
        for trigger, table in [('fbt_payment_balance', 'tracker_payment'), ('fbt_bill_balance', 'tracker_bill')]:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {trigger} ON {table}')
            schema_editor.execute(f'DROP FUNCTION IF EXISTS {trigger}_fn()')
    else:
        for trigger in ('fbt_payment_balance_insert', 'fbt_payment_balance_update', 'fbt_bill_balance'):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {trigger}')
