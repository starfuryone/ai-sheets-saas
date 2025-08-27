-- SaaS AI Functions Database Schema
-- PostgreSQL initialization script

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Teams table (created first due to foreign key dependencies)
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    owner_id UUID, -- Will be set after users table is created
    total_credits INTEGER DEFAULT 0,
    used_credits INTEGER DEFAULT 0,
    subscription_tier VARCHAR(50) DEFAULT 'team_basic',
    billing_email VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    subscription_tier VARCHAR(50) DEFAULT 'free',
    total_credits INTEGER DEFAULT 0,
    used_credits INTEGER DEFAULT 0,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    role VARCHAR(50) DEFAULT 'member', -- 'owner', 'admin', 'member'
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    email_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add foreign key constraint to teams table
ALTER TABLE teams ADD CONSTRAINT fk_teams_owner 
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;

-- Credits transaction log
CREATE TABLE credits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    transaction_type VARCHAR(50) NOT NULL, -- 'purchase', 'usage', 'refund', 'bonus', 'transfer'
    amount INTEGER NOT NULL, -- Positive for additions, negative for deductions
    balance_after INTEGER NOT NULL,
    description TEXT,
    stripe_payment_id VARCHAR(255),
    stripe_invoice_id VARCHAR(255),
    function_type VARCHAR(50), -- 'clean', 'seo', 'summarize'
    metadata JSONB, -- Additional data like function parameters
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage logs for detailed tracking and analytics
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    function_type VARCHAR(50) NOT NULL,
    input_data TEXT,
    output_data TEXT,
    input_length INTEGER,
    output_length INTEGER,
    credits_used INTEGER NOT NULL,
    execution_time_ms INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    error_code VARCHAR(50),
    ip_address INET,
    user_agent TEXT,
    sheets_document_id VARCHAR(255),
    sheets_sheet_name VARCHAR(255),
    sheets_cell_range VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subscription plans and pricing
CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    tier VARCHAR(50) UNIQUE NOT NULL,
    credits_included INTEGER NOT NULL,
    price_monthly INTEGER, -- Price in cents
    price_yearly INTEGER, -- Price in cents
    max_team_members INTEGER,
    features JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Credit packs for one-time purchases
CREATE TABLE credit_packs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    pack_type VARCHAR(50) UNIQUE NOT NULL,
    credits INTEGER NOT NULL,
    price INTEGER NOT NULL, -- Price in cents
    bonus_credits INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Team invitations
CREATE TABLE team_invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    invited_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'member',
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API keys for programmatic access
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    permissions JSONB, -- Array of allowed endpoints/functions
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rate limiting tracking
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identifier VARCHAR(255) NOT NULL, -- IP address, user ID, or API key
    endpoint VARCHAR(255) NOT NULL,
    requests_count INTEGER DEFAULT 1,
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    window_end TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, endpoint, window_start)
);

-- Webhooks for external integrations
CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    events TEXT[] NOT NULL, -- Array of event types
    secret VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance optimization

-- Users indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google_id ON users(google_id);
CREATE INDEX idx_users_team_id ON users(team_id);
CREATE INDEX idx_users_last_active ON users(last_active);
CREATE INDEX idx_users_subscription_tier ON users(subscription_tier);

-- Credits indexes
CREATE INDEX idx_credits_user_id ON credits(user_id);
CREATE INDEX idx_credits_team_id ON credits(team_id);
CREATE INDEX idx_credits_transaction_type ON credits(transaction_type);
CREATE INDEX idx_credits_created_at ON credits(created_at);
CREATE INDEX idx_credits_stripe_payment_id ON credits(stripe_payment_id);
CREATE INDEX idx_credits_function_type ON credits(function_type);

-- Usage logs indexes
CREATE INDEX idx_usage_logs_user_id ON usage_logs(user_id);
CREATE INDEX idx_usage_logs_team_id ON usage_logs(team_id);
CREATE INDEX idx_usage_logs_function_type ON usage_logs(function_type);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at);
CREATE INDEX idx_usage_logs_success ON usage_logs(success);
CREATE INDEX idx_usage_logs_monthly ON usage_logs(user_id, date_trunc('month', created_at));

-- Teams indexes
CREATE INDEX idx_teams_owner_id ON teams(owner_id);
CREATE INDEX idx_teams_subscription_tier ON teams(subscription_tier);

-- Team invitations indexes
CREATE INDEX idx_team_invitations_team_id ON team_invitations(team_id);
CREATE INDEX idx_team_invitations_email ON team_invitations(email);
CREATE INDEX idx_team_invitations_token ON team_invitations(token);
CREATE INDEX idx_team_invitations_expires_at ON team_invitations(expires_at);

-- API keys indexes
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_team_id ON api_keys(team_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_key_prefix ON api_keys(key_prefix);

-- Rate limits indexes
CREATE INDEX idx_rate_limits_identifier ON rate_limits(identifier);
CREATE INDEX idx_rate_limits_endpoint ON rate_limits(endpoint);
CREATE INDEX idx_rate_limits_window_end ON rate_limits(window_end);

-- Insert default subscription plans
INSERT INTO subscription_plans (name, tier, credits_included, price_monthly, price_yearly, max_team_members, features) VALUES
('Free', 'free', 10, 0, 0, 1, '{"api_access": false, "priority_support": false, "advanced_analytics": false}'),
('Starter', 'starter', 100, 999, 9990, 1, '{"api_access": true, "priority_support": false, "advanced_analytics": false}'),
('Professional', 'professional', 500, 2999, 29990, 5, '{"api_access": true, "priority_support": true, "advanced_analytics": true}'),
('Enterprise', 'enterprise', 2000, 9999, 99990, 25, '{"api_access": true, "priority_support": true, "advanced_analytics": true, "custom_integrations": true}'),
('Team Basic', 'team_basic', 1000, 4999, 49990, 10, '{"api_access": true, "priority_support": true, "advanced_analytics": true, "team_management": true}'),
('Team Pro', 'team_pro', 5000, 19999, 199990, 50, '{"api_access": true, "priority_support": true, "advanced_analytics": true, "team_management": true, "custom_integrations": true}');

-- Insert default credit packs
INSERT INTO credit_packs (name, pack_type, credits, price, bonus_credits) VALUES
('Starter Pack', 'starter', 100, 999, 10),
('Professional Pack', 'professional', 500, 3999, 75),
('Enterprise Pack', 'enterprise', 2000, 12999, 400),
('Mega Pack', 'mega', 5000, 24999, 1500);

-- Create functions for common operations

-- Function to get user's available credits
CREATE OR REPLACE FUNCTION get_user_available_credits(user_uuid UUID)
RETURNS INTEGER AS $$
DECLARE
    available_credits INTEGER;
BEGIN
    SELECT (total_credits - used_credits) INTO available_credits
    FROM users
    WHERE id = user_uuid;
    
    RETURN COALESCE(available_credits, 0);
END;
$$ LANGUAGE plpgsql;

-- Function to get monthly usage for a user
CREATE OR REPLACE FUNCTION get_user_monthly_usage(user_uuid UUID, target_month DATE DEFAULT CURRENT_DATE)
RETURNS TABLE(
    function_type VARCHAR(50),
    usage_count BIGINT,
    credits_used BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ul.function_type,
        COUNT(*) as usage_count,
        SUM(ul.credits_used) as credits_used
    FROM usage_logs ul
    WHERE ul.user_id = user_uuid
        AND ul.success = true
        AND date_trunc('month', ul.created_at) = date_trunc('month', target_month)
    GROUP BY ul.function_type;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up expired rate limits
CREATE OR REPLACE FUNCTION cleanup_expired_rate_limits()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM rate_limits
    WHERE window_end < CURRENT_TIMESTAMP - INTERVAL '1 hour';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up expired team invitations
CREATE OR REPLACE FUNCTION cleanup_expired_invitations()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM team_invitations
    WHERE expires_at < CURRENT_TIMESTAMP
        AND accepted_at IS NULL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update triggers to relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_teams_updated_at BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscription_plans_updated_at BEFORE UPDATE ON subscription_plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_credit_packs_updated_at BEFORE UPDATE ON credit_packs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for common queries

-- User dashboard view
CREATE VIEW user_dashboard AS
SELECT 
    u.id,
    u.email,
    u.name,
    u.subscription_tier,
    u.total_credits,
    u.used_credits,
    (u.total_credits - u.used_credits) AS available_credits,
    u.team_id,
    t.name AS team_name,
    u.role AS team_role,
    u.last_active,
    COALESCE(monthly_usage.total_usage, 0) AS usage_this_month
FROM users u
LEFT JOIN teams t ON u.team_id = t.id
LEFT JOIN (
    SELECT 
        user_id,
        SUM(credits_used) AS total_usage
    FROM usage_logs
    WHERE date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE)
        AND success = true
    GROUP BY user_id
) monthly_usage ON u.id = monthly_usage.user_id;

-- Team dashboard view
CREATE VIEW team_dashboard AS
SELECT 
    t.id,
    t.name,
    t.subscription_tier,
    t.total_credits,
    t.used_credits,
    (t.total_credits - t.used_credits) AS available_credits,
    COUNT(u.id) AS member_count,
    owner.name AS owner_name,
    owner.email AS owner_email,
    COALESCE(monthly_usage.total_usage, 0) AS usage_this_month
FROM teams t
LEFT JOIN users owner ON t.owner_id = owner.id
LEFT JOIN users u ON t.id = u.team_id
LEFT JOIN (
    SELECT 
        team_id,
        SUM(credits_used) AS total_usage
    FROM usage_logs
    WHERE date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE)
        AND success = true
        AND team_id IS NOT NULL
    GROUP BY team_id
) monthly_usage ON t.id = monthly_usage.team_id
GROUP BY t.id, t.name, t.subscription_tier, t.total_credits, t.used_credits, 
         owner.name, owner.email, monthly_usage.total_usage;

-- Usage analytics view
CREATE VIEW usage_analytics AS
SELECT 
    date_trunc('day', created_at) AS usage_date,
    function_type,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE success = true) AS successful_calls,
    COUNT(*) FILTER (WHERE success = false) AS failed_calls,
    SUM(credits_used) AS total_credits_used,
    AVG(execution_time_ms) AS avg_execution_time,
    COUNT(DISTINCT user_id) AS unique_users
FROM usage_logs
GROUP BY date_trunc('day', created_at), function_type
ORDER BY usage_date DESC, function_type;

-- Grant permissions (adjust as needed for your environment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO your_app_user;

-- Create indexes for better query performance on large datasets
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_logs_user_month 
    ON usage_logs (user_id, date_trunc('month', created_at));

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_logs_team_month 
    ON usage_logs (team_id, date_trunc('month', created_at)) 
    WHERE team_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_user_month 
    ON credits (user_id, date_trunc('month', created_at));

-- Comments for documentation
COMMENT ON TABLE users IS 'User accounts and authentication information';
COMMENT ON TABLE teams IS 'Team/organization accounts for collaborative usage';
COMMENT ON TABLE credits IS 'Credit transaction log for purchases and usage';
COMMENT ON TABLE usage_logs IS 'Detailed logs of AI function usage';
COMMENT ON TABLE subscription_plans IS 'Available subscription tiers and pricing';
COMMENT ON TABLE credit_packs IS 'One-time credit purchase options';
COMMENT ON TABLE team_invitations IS 'Pending team member invitations';
COMMENT ON TABLE api_keys IS 'API keys for programmatic access';
COMMENT ON TABLE rate_limits IS 'Rate limiting tracking data';
COMMENT ON TABLE webhooks IS 'Webhook configurations for external integrations';

COMMENT ON FUNCTION get_user_available_credits(UUID) IS 'Calculate available credits for a user';
COMMENT ON FUNCTION get_user_monthly_usage(UUID, DATE) IS 'Get monthly usage statistics for a user';
COMMENT ON FUNCTION cleanup_expired_rate_limits() IS 'Remove old rate limiting records';
COMMENT ON FUNCTION cleanup_expired_invitations() IS 'Remove expired team invitations';

