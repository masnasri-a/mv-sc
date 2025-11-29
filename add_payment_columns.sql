-- Add new columns to payments table for Saweria webhook v2 format
-- Run this in your Supabase SQL Editor

-- Add amount_display column (display amount shown to user)
ALTER TABLE payments ADD COLUMN IF NOT EXISTS amount_display INTEGER;

-- Add qr_string column (QR code string from Saweria)
ALTER TABLE payments ADD COLUMN IF NOT EXISTS qr_string TEXT;

-- Update existing records to set amount_display = amount if null
UPDATE payments SET amount_display = amount WHERE amount_display IS NULL;

-- Add comments to document the columns
COMMENT ON COLUMN payments.amount IS 'Raw amount from Saweria webhook (amount_raw field)';
COMMENT ON COLUMN payments.amount_display IS 'Display amount shown to user (etc.amount_to_display field)';
COMMENT ON COLUMN payments.qr_string IS 'QR code string from Saweria webhook (etc.qr_string field)';