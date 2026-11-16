"""baseline schema

Revision ID: 0be45af65a74
Revises: 
Create Date: 2026-10-29 10:42:59.014040
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0be45af65a74'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('commodities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('product_form', sa.String(length=40), nullable=False),
    sa.Column('name_te', sa.String(length=80), nullable=True),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('handling_class', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('commodities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_commodities_category'), ['category'], unique=False)

    op.create_table('grade_specs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('commodity_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=24), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('attributes', sa.JSON(), nullable=True),
    sa.Column('spec_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['commodity_id'], ['commodities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('grade_specs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_grade_specs_commodity_id'), ['commodity_id'], unique=False)

    op.create_table('states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('code', sa.String(length=10), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    sa.UniqueConstraint('name')
    )
    op.create_table('districts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['state_id'], ['states.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_districts_state_id'), ['state_id'], unique=False)

    op.create_table('mandals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('district_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('serviceable', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mandals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mandals_district_id'), ['district_id'], unique=False)

    op.create_table('organisations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=False),
    sa.Column('verification_status', sa.String(length=16), nullable=False),
    sa.Column('licence_refs', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('preferred_language', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('consent_at', sa.String(length=40), nullable=True),
    sa.Column('onboarding_complete', sa.Boolean(), nullable=False),
    sa.Column('organisation_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_organisation_id'), ['organisation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_phone'), ['phone'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_role'), ['role'], unique=False)

    op.create_table('varieties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('commodity_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('name_te', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['commodity_id'], ['commodities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_varieties_commodity_id'), ['commodity_id'], unique=False)

    op.create_table('listings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('commodity_id', sa.Integer(), nullable=False),
    sa.Column('variety_id', sa.Integer(), nullable=True),
    sa.Column('grade_spec_id', sa.Integer(), nullable=True),
    sa.Column('harvest_year', sa.Integer(), nullable=True),
    sa.Column('available_from', sa.Date(), nullable=True),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('total_qty', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('reserved_qty', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('sold_qty', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('min_order_qty', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('asking_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('negotiable', sa.Boolean(), nullable=False),
    sa.Column('claim_status', sa.String(length=16), nullable=False),
    sa.Column('claim_evidence', sa.JSON(), nullable=True),
    sa.Column('mandal_id', sa.Integer(), nullable=True),
    sa.Column('pickup_terms', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['commodity_id'], ['commodities.id'], ),
    sa.ForeignKeyConstraint(['grade_spec_id'], ['grade_specs.id'], ),
    sa.ForeignKeyConstraint(['mandal_id'], ['mandals.id'], ),
    sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['variety_id'], ['varieties.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_listings_commodity_id'), ['commodity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_listings_mandal_id'), ['mandal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_listings_seller_id'), ['seller_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_listings_status'), ['status'], unique=False)

    op.create_table('rfqs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('buyer_id', sa.Integer(), nullable=False),
    sa.Column('commodity_id', sa.Integer(), nullable=False),
    sa.Column('variety_id', sa.Integer(), nullable=True),
    sa.Column('grade_spec_id', sa.Integer(), nullable=True),
    sa.Column('requested_qty', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('target_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('destination_mandal_id', sa.Integer(), nullable=True),
    sa.Column('delivery_window', sa.String(length=80), nullable=True),
    sa.Column('packaging', sa.String(length=80), nullable=True),
    sa.Column('acceptable_variation', sa.JSON(), nullable=True),
    sa.Column('inspection_required', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['commodity_id'], ['commodities.id'], ),
    sa.ForeignKeyConstraint(['destination_mandal_id'], ['mandals.id'], ),
    sa.ForeignKeyConstraint(['grade_spec_id'], ['grade_specs.id'], ),
    sa.ForeignKeyConstraint(['variety_id'], ['varieties.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rfqs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rfqs_buyer_id'), ['buyer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rfqs_commodity_id'), ['commodity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rfqs_status'), ['status'], unique=False)

    op.create_table('offers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=True),
    sa.Column('rfq_id', sa.Integer(), nullable=True),
    sa.Column('buyer_id', sa.Integer(), nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('accepted_version_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], ),
    sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_offers_buyer_id'), ['buyer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_offers_listing_id'), ['listing_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_offers_rfq_id'), ['rfq_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_offers_seller_id'), ['seller_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_offers_status'), ['status'], unique=False)

    op.create_table('offer_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('offer_id', sa.Integer(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('proposer_role', sa.String(length=8), nullable=False),
    sa.Column('proposer_id', sa.Integer(), nullable=False),
    sa.Column('price_per_unit', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('grade_spec_id', sa.Integer(), nullable=True),
    sa.Column('delivery_terms', sa.JSON(), nullable=True),
    sa.Column('inspection_conditions', sa.JSON(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['grade_spec_id'], ['grade_specs.id'], ),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ),
    sa.ForeignKeyConstraint(['proposer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('offer_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_offer_versions_offer_id'), ['offer_id'], unique=False)

    op.create_table('agent_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('skill_level', sa.String(length=40), nullable=False),
    sa.Column('service_mandals', sa.JSON(), nullable=True),
    sa.Column('languages', sa.String(length=120), nullable=True),
    sa.Column('equipment', sa.JSON(), nullable=True),
    sa.Column('training_modules', sa.JSON(), nullable=True),
    sa.Column('supervisor_id', sa.Integer(), nullable=True),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('performance_status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['supervisor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('object_type', sa.String(length=40), nullable=True),
    sa.Column('object_id', sa.String(length=40), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('old_values', sa.JSON(), nullable=True),
    sa.Column('new_values', sa.JSON(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_actor_id'), ['actor_id'], unique=False)

    op.create_table('buyer_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('buyer_type', sa.String(length=16), nullable=False),
    sa.Column('delivery_zones', sa.JSON(), nullable=True),
    sa.Column('billing', sa.JSON(), nullable=True),
    sa.Column('verification_status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('public_id', sa.String(length=20), nullable=False),
    sa.Column('buyer_id', sa.Integer(), nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('offer_id', sa.Integer(), nullable=True),
    sa.Column('assigned_agent_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('accepted_terms', sa.JSON(), nullable=False),
    sa.Column('quote', sa.JSON(), nullable=True),
    sa.Column('pricing_rule_version', sa.Integer(), nullable=True),
    sa.Column('cancellation_policy_version', sa.Integer(), nullable=False),
    sa.Column('buyer_total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('seller_payable', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_agent_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ),
    sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_orders_assigned_agent_id'), ['assigned_agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_buyer_id'), ['buyer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_public_id'), ['public_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_orders_seller_id'), ['seller_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_status'), ['status'], unique=False)

    op.create_table('farmer_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('state_id', sa.Integer(), nullable=True),
    sa.Column('district_id', sa.Integer(), nullable=True),
    sa.Column('mandal_id', sa.Integer(), nullable=True),
    sa.Column('village', sa.String(length=120), nullable=True),
    sa.Column('pickup_point', sa.String(length=200), nullable=True),
    sa.Column('payout_beneficiary_ref', sa.String(length=80), nullable=True),
    sa.Column('verification_status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ),
    sa.ForeignKeyConstraint(['mandal_id'], ['mandals.id'], ),
    sa.ForeignKeyConstraint(['state_id'], ['states.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    with op.batch_alter_table('farmer_profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_farmer_profiles_mandal_id'), ['mandal_id'], unique=False)

    op.create_table('ledger_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('txn_group', sa.String(length=64), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('account', sa.String(length=40), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=4), nullable=False),
    sa.Column('memo', sa.Text(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ledger_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ledger_entries_account'), ['account'], unique=False)
        batch_op.create_index(batch_op.f('ix_ledger_entries_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ledger_entries_txn_group'), ['txn_group'], unique=False)

    op.create_table('order_status_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('reason_code', sa.String(length=40), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('order_status_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_order_status_events_order_id'), ['order_id'], unique=False)

    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('provider_ref', sa.String(length=120), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=4), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_idempotency_key'), ['idempotency_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_payments_order_id'), ['order_id'], unique=False)

    op.create_table('payouts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=4), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('provider_ref', sa.String(length=120), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payouts_idempotency_key'), ['idempotency_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_payouts_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payouts_seller_id'), ['seller_id'], unique=False)

    op.create_table('pricing_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('service_mandal_id', sa.Integer(), nullable=True),
    sa.Column('handling_class', sa.String(length=24), nullable=True),
    sa.Column('currency', sa.String(length=4), nullable=False),
    sa.Column('rate_per_kg', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('rate_per_km', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('fixed_pickup_fee', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('min_transport_charge', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('max_transport_charge', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('service_fee_pct', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('service_fee_flat', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('service_fee_payer', sa.String(length=8), nullable=False),
    sa.Column('inspection_fee', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('packing_fee', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('tax_pct', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('surcharges', sa.JSON(), nullable=True),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=300), nullable=True),
    sa.Column('requires_second_approval', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['service_mandal_id'], ['mandals.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pricing_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pricing_rules_version'), ['version'], unique=False)

    op.create_table('shipments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('public_id', sa.String(length=20), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('carrier_id', sa.Integer(), nullable=True),
    sa.Column('route', sa.JSON(), nullable=True),
    sa.Column('vehicle_class', sa.String(length=40), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('eta_source', sa.String(length=40), nullable=True),
    sa.Column('proof_of_delivery', sa.JSON(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['carrier_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shipments_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipments_public_id'), ['public_id'], unique=True)

    op.create_table('listing_media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('object_key', sa.String(length=300), nullable=False),
    sa.Column('media_type', sa.String(length=16), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=True),
    sa.Column('access_class', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('listing_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_listing_media_listing_id'), ['listing_id'], unique=False)

    op.create_table('lots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('public_id', sa.String(length=20), nullable=False),
    sa.Column('parent_lot_id', sa.Integer(), nullable=True),
    sa.Column('source_listing_id', sa.Integer(), nullable=True),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('commodity_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('grade_spec_id', sa.Integer(), nullable=True),
    sa.Column('seal_ref', sa.String(length=80), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['commodity_id'], ['commodities.id'], ),
    sa.ForeignKeyConstraint(['grade_spec_id'], ['grade_specs.id'], ),
    sa.ForeignKeyConstraint(['parent_lot_id'], ['lots.id'], ),
    sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['source_listing_id'], ['listings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('lots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lots_public_id'), ['public_id'], unique=True)

    op.create_table('shipment_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shipment_id', sa.Integer(), nullable=False),
    sa.Column('event', sa.String(length=40), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('location_precision', sa.String(length=24), nullable=True),
    sa.Column('evidence_ref', sa.String(length=300), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('shipment_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shipment_events_shipment_id'), ['shipment_id'], unique=False)

    op.create_table('inspections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.Integer(), nullable=True),
    sa.Column('agent_id', sa.Integer(), nullable=False),
    sa.Column('declared_qty', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('gross_weight', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('tare_weight', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('net_qty', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('scale_ref', sa.String(length=80), nullable=True),
    sa.Column('checklist', sa.JSON(), nullable=True),
    sa.Column('measurements', sa.JSON(), nullable=True),
    sa.Column('evidence', sa.JSON(), nullable=True),
    sa.Column('outcome', sa.String(length=24), nullable=True),
    sa.Column('reason_codes', sa.JSON(), nullable=True),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('client_draft_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_draft_id')
    )
    with op.batch_alter_table('inspections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inspections_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inspections_order_id'), ['order_id'], unique=False)

    op.create_table('lot_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('lot_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lot_events_lot_id'), ['lot_id'], unique=False)

    op.create_table('order_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=True),
    sa.Column('lot_id', sa.Integer(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('accepted_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('price_per_unit', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('grade_spec_id', sa.Integer(), nullable=True),
    sa.Column('allocation_status', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['grade_spec_id'], ['grade_specs.id'], ),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('order_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_order_lines_order_id'), ['order_id'], unique=False)

    op.create_table('packages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.Integer(), nullable=False),
    sa.Column('qr_code', sa.String(length=40), nullable=False),
    sa.Column('net_weight', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('package_count', sa.Integer(), nullable=False),
    sa.Column('label_data', sa.JSON(), nullable=True),
    sa.Column('packing_status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('packages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_packages_lot_id'), ['lot_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_packages_qr_code'), ['qr_code'], unique=True)

    # ### end Alembic commands ###


    # ### commands auto generated by Alembic - please adjust! ###
    # Circular FK (offers.accepted_version_id -> offer_versions) added after
    # both tables exist; batch_alter_table works on SQLite and Postgres.
    with op.batch_alter_table('offers') as batch_op:
        batch_op.create_foreign_key(
            'fk_offers_accepted_version_id_offer_versions',
            'offer_versions', ['accepted_version_id'], ['id'])


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('packages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_packages_qr_code'))
        batch_op.drop_index(batch_op.f('ix_packages_lot_id'))

    op.drop_table('packages')
    with op.batch_alter_table('order_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_order_lines_order_id'))

    op.drop_table('order_lines')
    with op.batch_alter_table('lot_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lot_events_lot_id'))

    op.drop_table('lot_events')
    with op.batch_alter_table('inspections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inspections_order_id'))
        batch_op.drop_index(batch_op.f('ix_inspections_agent_id'))

    op.drop_table('inspections')
    with op.batch_alter_table('shipment_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shipment_events_shipment_id'))

    op.drop_table('shipment_events')
    with op.batch_alter_table('lots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lots_public_id'))

    op.drop_table('lots')
    with op.batch_alter_table('listing_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listing_media_listing_id'))

    op.drop_table('listing_media')
    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shipments_public_id'))
        batch_op.drop_index(batch_op.f('ix_shipments_order_id'))

    op.drop_table('shipments')
    with op.batch_alter_table('rfqs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rfqs_status'))
        batch_op.drop_index(batch_op.f('ix_rfqs_commodity_id'))
        batch_op.drop_index(batch_op.f('ix_rfqs_buyer_id'))

    op.drop_table('rfqs')
    with op.batch_alter_table('pricing_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pricing_rules_version'))

    op.drop_table('pricing_rules')
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payouts_seller_id'))
        batch_op.drop_index(batch_op.f('ix_payouts_order_id'))
        batch_op.drop_index(batch_op.f('ix_payouts_idempotency_key'))

    op.drop_table('payouts')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_order_id'))
        batch_op.drop_index(batch_op.f('ix_payments_idempotency_key'))

    op.drop_table('payments')
    with op.batch_alter_table('order_status_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_order_status_events_order_id'))

    op.drop_table('order_status_events')
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_status'))
        batch_op.drop_index(batch_op.f('ix_listings_seller_id'))
        batch_op.drop_index(batch_op.f('ix_listings_mandal_id'))
        batch_op.drop_index(batch_op.f('ix_listings_commodity_id'))

    op.drop_table('listings')
    with op.batch_alter_table('ledger_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ledger_entries_txn_group'))
        batch_op.drop_index(batch_op.f('ix_ledger_entries_order_id'))
        batch_op.drop_index(batch_op.f('ix_ledger_entries_account'))

    op.drop_table('ledger_entries')
    with op.batch_alter_table('farmer_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_farmer_profiles_mandal_id'))

    op.drop_table('farmer_profiles')
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_orders_status'))
        batch_op.drop_index(batch_op.f('ix_orders_seller_id'))
        batch_op.drop_index(batch_op.f('ix_orders_public_id'))
        batch_op.drop_index(batch_op.f('ix_orders_buyer_id'))
        batch_op.drop_index(batch_op.f('ix_orders_assigned_agent_id'))

    op.drop_table('orders')
    with op.batch_alter_table('mandals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mandals_district_id'))

    op.drop_table('mandals')
    op.drop_table('buyer_profiles')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_actor_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_action'))

    op.drop_table('audit_logs')
    op.drop_table('agent_profiles')
    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_varieties_commodity_id'))

    op.drop_table('varieties')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_role'))
        batch_op.drop_index(batch_op.f('ix_users_phone'))
        batch_op.drop_index(batch_op.f('ix_users_organisation_id'))

    op.drop_table('users')
    with op.batch_alter_table('grade_specs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_grade_specs_commodity_id'))

    op.drop_table('grade_specs')
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_districts_state_id'))

    op.drop_table('districts')
    op.drop_table('states')
    op.drop_table('organisations')
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_offers_status'))
        batch_op.drop_index(batch_op.f('ix_offers_seller_id'))
        batch_op.drop_index(batch_op.f('ix_offers_rfq_id'))
        batch_op.drop_index(batch_op.f('ix_offers_listing_id'))
        batch_op.drop_index(batch_op.f('ix_offers_buyer_id'))

    op.drop_table('offers')
    with op.batch_alter_table('offer_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_offer_versions_offer_id'))

    op.drop_table('offer_versions')
    with op.batch_alter_table('commodities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commodities_category'))

    op.drop_table('commodities')
    # ### end Alembic commands ###
