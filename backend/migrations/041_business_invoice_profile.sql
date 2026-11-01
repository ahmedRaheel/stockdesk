ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS branch_name text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS shop_number text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS business_type text NOT NULL DEFAULT 'retail',
    ADD COLUMN IF NOT EXISTS phone text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS email text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS website text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ntn text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS strn text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS invoice_title text NOT NULL DEFAULT 'CASH INVOICE',
    ADD COLUMN IF NOT EXISTS invoice_header text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS invoice_footer text NOT NULL DEFAULT 'Thank you for your business.',
    ADD COLUMN IF NOT EXISTS return_policy text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS exchange_policy text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS pos_charge_label text NOT NULL DEFAULT 'POS Charges',
    ADD COLUMN IF NOT EXISTS pos_charge bigint NOT NULL DEFAULT 0 CHECK (pos_charge >= 0),
    ADD COLUMN IF NOT EXISTS receipt_width text NOT NULL DEFAULT '80mm'
        CHECK (receipt_width IN ('58mm','80mm','A4')),
    ADD COLUMN IF NOT EXISTS logo_url text NOT NULL DEFAULT '';

ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS seller_profile jsonb NOT NULL DEFAULT '{}'::jsonb;
