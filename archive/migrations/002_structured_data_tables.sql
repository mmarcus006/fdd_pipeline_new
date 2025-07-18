-- Structured Data Tables for High-Value FDD Sections
-- Items 5, 6, 7, 19, 20, 21

-- Item 5: Initial franchise fees
CREATE TABLE item5_initial_fees (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fee_name TEXT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    refundable BOOLEAN DEFAULT false,
    refund_conditions TEXT,
    due_at TEXT, -- 'Signing', 'Training', 'Opening'
    notes TEXT,
    
    PRIMARY KEY (section_id, fee_name)
);

-- Item 6: Ongoing and other fees
CREATE TABLE item6_other_fees (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fee_name TEXT NOT NULL,
    amount_cents BIGINT CHECK (amount_cents >= 0),
    amount_percentage NUMERIC(5,2) CHECK (amount_percentage >= 0 AND amount_percentage <= 100),
    frequency TEXT NOT NULL, -- 'Weekly', 'Monthly', 'Annual', 'One-time'
    calculation_basis TEXT, -- 'Gross Sales', 'Net Sales', 'Fixed'
    minimum_cents BIGINT CHECK (minimum_cents >= 0),
    maximum_cents BIGINT CHECK (maximum_cents >= minimum_cents),
    remarks TEXT,
    
    PRIMARY KEY (section_id, fee_name),
    CONSTRAINT check_amount_or_percentage CHECK (
        (amount_cents IS NOT NULL AND amount_percentage IS NULL) OR
        (amount_cents IS NULL AND amount_percentage IS NOT NULL)
    )
);

-- Item 7: Initial investment breakdown
CREATE TABLE item7_initial_investment (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    low_cents BIGINT CHECK (low_cents >= 0),
    high_cents BIGINT CHECK (high_cents >= low_cents),
    when_due TEXT,
    to_whom TEXT,
    remarks TEXT,
    
    PRIMARY KEY (section_id, category)
);

-- Item 19: Financial Performance Representations
CREATE TABLE item19_fpr (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    disclosure_type TEXT, -- 'Historical', 'Projected', 'None'
    methodology TEXT, -- narrative description
    sample_size INTEGER CHECK (sample_size > 0),
    sample_description TEXT,
    time_period TEXT,
    
    -- Common financial metrics (all nullable)
    average_revenue_cents BIGINT CHECK (average_revenue_cents >= 0),
    median_revenue_cents BIGINT CHECK (median_revenue_cents >= 0),
    low_revenue_cents BIGINT CHECK (low_revenue_cents >= 0),
    high_revenue_cents BIGINT CHECK (high_revenue_cents >= 0),
    
    average_profit_cents BIGINT,
    median_profit_cents BIGINT,
    profit_margin_percentage NUMERIC(5,2),
    
    -- For complex/varied data
    additional_metrics JSONB DEFAULT '{}'::jsonb,
    tables_data JSONB DEFAULT '[]'::jsonb, -- array of table representations
    
    disclaimers TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Item 20: Outlet summary by year
CREATE TABLE item20_outlet_summary (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fiscal_year SMALLINT NOT NULL CHECK (fiscal_year >= 1900 AND fiscal_year <= 2100),
    outlet_type TEXT NOT NULL CHECK (outlet_type IN ('Franchised', 'Company-Owned')),
    
    -- Annual movements
    count_start INTEGER NOT NULL CHECK (count_start >= 0),
    opened INTEGER NOT NULL DEFAULT 0 CHECK (opened >= 0),
    closed INTEGER NOT NULL DEFAULT 0 CHECK (closed >= 0),
    transferred_in INTEGER NOT NULL DEFAULT 0 CHECK (transferred_in >= 0),
    transferred_out INTEGER NOT NULL DEFAULT 0 CHECK (transferred_out >= 0),
    count_end INTEGER NOT NULL CHECK (count_end >= 0),
    
    -- Calculated check
    CONSTRAINT outlet_math_check CHECK (
        count_end = count_start + opened - closed + transferred_in - transferred_out
    ),
    
    PRIMARY KEY (section_id, fiscal_year, outlet_type)
);

-- Item 20: State-by-state breakdown
CREATE TABLE item20_state_counts (
    section_id UUID REFERENCES fdd_sections(id) ON DELETE CASCADE,
    state_code CHAR(2) NOT NULL,
    franchised_count INTEGER DEFAULT 0 CHECK (franchised_count >= 0),
    company_owned_count INTEGER DEFAULT 0 CHECK (company_owned_count >= 0),
    
    PRIMARY KEY (section_id, state_code)
);

-- Item 21: Financial statements
CREATE TABLE item21_financials (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    fiscal_year SMALLINT CHECK (fiscal_year >= 1900 AND fiscal_year <= 2100),
    fiscal_year_end DATE,
    
    -- Income Statement
    total_revenue_cents BIGINT CHECK (total_revenue_cents >= 0),
    franchise_revenue_cents BIGINT CHECK (franchise_revenue_cents >= 0),
    cost_of_goods_cents BIGINT CHECK (cost_of_goods_cents >= 0),
    gross_profit_cents BIGINT,
    operating_expenses_cents BIGINT CHECK (operating_expenses_cents >= 0),
    operating_income_cents BIGINT,
    net_income_cents BIGINT,
    
    -- Balance Sheet
    total_assets_cents BIGINT CHECK (total_assets_cents >= 0),
    current_assets_cents BIGINT CHECK (current_assets_cents >= 0),
    total_liabilities_cents BIGINT CHECK (total_liabilities_cents >= 0),
    current_liabilities_cents BIGINT CHECK (current_liabilities_cents >= 0),
    total_equity_cents BIGINT,
    
    -- Audit info
    auditor_name TEXT,
    audit_opinion TEXT,
    
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Generic storage for all other items
CREATE TABLE fdd_item_json (
    section_id UUID PRIMARY KEY REFERENCES fdd_sections(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT DEFAULT '1.0',
    validated BOOLEAN DEFAULT false,
    validation_errors JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for querying specific fields within JSON
CREATE INDEX idx_fdd_item_json_data ON fdd_item_json USING gin(data);