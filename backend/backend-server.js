/**
 * SaaS AI Functions Backend Server
 * Main server file with Express.js and API routes
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');
const { Pool } = require('pg');
const Redis = require('redis');
const OpenAI = require('openai');
const stripe = require('stripe');
require('dotenv').config();

// Initialize Express app
const app = express();
const PORT = process.env.PORT || 3000;

// Initialize external services
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const stripeClient = stripe(process.env.STRIPE_SECRET_KEY);

// Database connection
const db = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
});

// Redis connection
const redis = Redis.createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379',
});

redis.on('error', (err) => {
  console.error('Redis connection error:', err);
});

redis.connect();

// Middleware
app.use(helmet());
app.use(cors({
  origin: '*', // Allow all origins for Google Sheets integration
  credentials: true,
}));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // Limit each IP to 100 requests per windowMs
  message: {
    error: 'Too many requests from this IP, please try again later.',
  },
});

app.use('/api/', limiter);

// More restrictive rate limiting for AI functions
const aiLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 20, // Limit each IP to 20 AI requests per minute
  message: {
    error: 'AI function rate limit exceeded, please try again later.',
  },
});

app.use('/api/functions/', aiLimiter);

// Credit costs for different functions
const CREDIT_COSTS = {
  clean: 1,
  seo: 2,
  summarize: 1,
};

// Credit pack configurations
const CREDIT_PACKS = {
  starter: { credits: 100, price: 999 }, // $9.99
  professional: { credits: 500, price: 3999 }, // $39.99
  enterprise: { credits: 2000, price: 12999 }, // $129.99
};

// Free trial credits
const FREE_TRIAL_CREDITS = 10;

// Authentication middleware
const authenticateToken = async (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: 'Access token required' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    
    // Get user from database
    const userResult = await db.query(
      'SELECT * FROM users WHERE id = $1',
      [decoded.userId]
    );

    if (userResult.rows.length === 0) {
      return res.status(401).json({ error: 'Invalid token' });
    }

    req.user = userResult.rows[0];
    next();
  } catch (error) {
    console.error('Token verification error:', error);
    return res.status(403).json({ error: 'Invalid or expired token' });
  }
};

// Check credits middleware
const checkCredits = (functionType) => {
  return async (req, res, next) => {
    const creditCost = CREDIT_COSTS[functionType] || 1;
    const availableCredits = req.user.total_credits - req.user.used_credits;

    if (availableCredits < creditCost) {
      return res.status(402).json({
        error: 'Insufficient credits',
        required: creditCost,
        available: availableCredits,
      });
    }

    req.creditCost = creditCost;
    next();
  };
};

// Utility function to deduct credits
const deductCredits = async (userId, amount, functionType, description) => {
  const client = await db.connect();
  
  try {
    await client.query('BEGIN');

    // Update user credits
    const updateResult = await client.query(
      'UPDATE users SET used_credits = used_credits + $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2 RETURNING total_credits, used_credits',
      [amount, userId]
    );

    const user = updateResult.rows[0];
    const balanceAfter = user.total_credits - user.used_credits;

    // Log credit transaction
    await client.query(
      'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description, function_type) VALUES ($1, $2, $3, $4, $5, $6)',
      [userId, 'usage', -amount, balanceAfter, description, functionType]
    );

    await client.query('COMMIT');
    return balanceAfter;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
};

// Utility function to add credits
const addCredits = async (userId, amount, description, stripePaymentId = null) => {
  const client = await db.connect();
  
  try {
    await client.query('BEGIN');

    // Update user credits
    const updateResult = await client.query(
      'UPDATE users SET total_credits = total_credits + $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2 RETURNING total_credits, used_credits',
      [amount, userId]
    );

    const user = updateResult.rows[0];
    const balanceAfter = user.total_credits - user.used_credits;

    // Log credit transaction
    await client.query(
      'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description, stripe_payment_id) VALUES ($1, $2, $3, $4, $5, $6)',
      [userId, 'purchase', amount, balanceAfter, description, stripePaymentId]
    );

    await client.query('COMMIT');
    return balanceAfter;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
};

// Routes

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Authentication routes
app.post('/api/auth/google', async (req, res) => {
  try {
    const { google_token } = req.body;

    if (!google_token) {
      return res.status(400).json({ error: 'Google token required' });
    }

    // Verify Google token (simplified - in production, verify with Google)
    // For now, we'll extract user info from the token payload
    const googleResponse = await fetch(`https://www.googleapis.com/oauth2/v1/userinfo?access_token=${google_token}`);
    const googleUser = await googleResponse.json();

    if (!googleUser.email) {
      return res.status(400).json({ error: 'Invalid Google token' });
    }

    // Check if user exists
    let userResult = await db.query(
      'SELECT * FROM users WHERE email = $1',
      [googleUser.email]
    );

    let user;
    if (userResult.rows.length === 0) {
      // Create new user with free trial credits
      const insertResult = await db.query(
        'INSERT INTO users (email, google_id, name, avatar_url, total_credits) VALUES ($1, $2, $3, $4, $5) RETURNING *',
        [googleUser.email, googleUser.id, googleUser.name, googleUser.picture, FREE_TRIAL_CREDITS]
      );
      user = insertResult.rows[0];

      // Log free trial credits
      await db.query(
        'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description) VALUES ($1, $2, $3, $4, $5)',
        [user.id, 'bonus', FREE_TRIAL_CREDITS, FREE_TRIAL_CREDITS, 'Free trial credits']
      );
    } else {
      user = userResult.rows[0];
      
      // Update last active
      await db.query(
        'UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = $1',
        [user.id]
      );
    }

    // Generate JWT token
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      process.env.JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        credits: user.total_credits - user.used_credits,
        subscription_tier: user.subscription_tier,
      },
      jwt_token: token,
    });
  } catch (error) {
    console.error('Authentication error:', error);
    res.status(500).json({ error: 'Authentication failed' });
  }
});

// Credit management routes
app.get('/api/credits/balance', authenticateToken, async (req, res) => {
  try {
    // Get current month usage
    const usageResult = await db.query(
      `SELECT 
        function_type,
        COUNT(*) as count,
        SUM(ABS(amount)) as credits_used
      FROM credits 
      WHERE user_id = $1 
        AND transaction_type = 'usage' 
        AND created_at >= date_trunc('month', CURRENT_DATE)
      GROUP BY function_type`,
      [req.user.id]
    );

    const usage = {};
    let totalUsageThisMonth = 0;
    
    usageResult.rows.forEach(row => {
      usage[row.function_type] = parseInt(row.count);
      totalUsageThisMonth += parseInt(row.credits_used);
    });

    res.json({
      success: true,
      total_credits: req.user.total_credits,
      used_credits: req.user.used_credits,
      available_credits: req.user.total_credits - req.user.used_credits,
      usage_this_month: totalUsageThisMonth,
      subscription_tier: req.user.subscription_tier,
      usage: usage,
    });
  } catch (error) {
    console.error('Error fetching credits:', error);
    res.status(500).json({ error: 'Failed to fetch credit balance' });
  }
});

// AI Function routes
app.post('/api/functions/clean', authenticateToken, checkCredits('clean'), async (req, res) => {
  try {
    const { data, options = {} } = req.body;

    if (!data) {
      return res.status(400).json({ error: 'Data is required' });
    }

    // Prepare prompt for data cleaning
    let prompt = `Clean and normalize the following data:\n\n"${data}"\n\nInstructions:\n`;
    
    if (options.strip_formatting) {
      prompt += '- Remove any formatting characters and extra whitespace\n';
    }
    
    if (options.normalize_case && options.normalize_case !== 'none') {
      prompt += `- Convert text to ${options.normalize_case} case\n`;
    }
    
    if (options.remove_duplicates) {
      prompt += '- Remove any duplicate content\n';
    }
    
    prompt += '\nReturn only the cleaned data without any explanations.';

    // Call OpenAI API
    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'You are a data cleaning assistant. Clean and normalize data according to the given instructions. Return only the cleaned result without explanations.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
      max_tokens: 500,
      temperature: 0.1,
    });

    const result = completion.choices[0].message.content.trim();

    // Deduct credits
    const remainingCredits = await deductCredits(
      req.user.id,
      req.creditCost,
      'clean',
      `Data cleaning: ${data.substring(0, 50)}...`
    );

    // Log usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, output_data, credits_used, success) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'clean', data, result, req.creditCost, true]
    );

    res.json({
      success: true,
      result: result,
      credits_used: req.creditCost,
      remaining_credits: remainingCredits,
    });
  } catch (error) {
    console.error('Data cleaning error:', error);
    
    // Log failed usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, credits_used, success, error_message) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'clean', req.body.data, 0, false, error.message]
    );

    res.status(500).json({ error: 'Data cleaning failed' });
  }
});

app.post('/api/functions/seo', authenticateToken, checkCredits('seo'), async (req, res) => {
  try {
    const { content, seo_type, target_keywords = [], max_length = 160 } = req.body;

    if (!content) {
      return res.status(400).json({ error: 'Content is required' });
    }

    let prompt = '';
    
    switch (seo_type) {
      case 'keywords':
        prompt = `Extract the most relevant SEO keywords from the following content:\n\n"${content}"\n\nReturn a comma-separated list of keywords.`;
        break;
      case 'meta_description':
        prompt = `Write an SEO-optimized meta description (max ${max_length} characters) for the following content:\n\n"${content}"`;
        if (target_keywords.length > 0) {
          prompt += `\n\nInclude these keywords: ${target_keywords.join(', ')}`;
        }
        break;
      case 'ad_copy':
        prompt = `Write compelling ad copy for the following content:\n\n"${content}"`;
        if (target_keywords.length > 0) {
          prompt += `\n\nTarget keywords: ${target_keywords.join(', ')}`;
        }
        break;
      default:
        return res.status(400).json({ error: 'Invalid SEO type' });
    }

    // Call OpenAI API
    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'You are an SEO expert. Create optimized content according to the user\'s requirements.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
      max_tokens: 300,
      temperature: 0.3,
    });

    const result = completion.choices[0].message.content.trim();

    // Deduct credits
    const remainingCredits = await deductCredits(
      req.user.id,
      req.creditCost,
      'seo',
      `SEO ${seo_type}: ${content.substring(0, 50)}...`
    );

    // Log usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, output_data, credits_used, success) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'seo', content, result, req.creditCost, true]
    );

    res.json({
      success: true,
      result: result,
      credits_used: req.creditCost,
      remaining_credits: remainingCredits,
    });
  } catch (error) {
    console.error('SEO processing error:', error);
    
    // Log failed usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, credits_used, success, error_message) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'seo', req.body.content, 0, false, error.message]
    );

    res.status(500).json({ error: 'SEO processing failed' });
  }
});

app.post('/api/functions/summarize', authenticateToken, checkCredits('summarize'), async (req, res) => {
  try {
    const { text, max_length = 150, style = 'paragraph' } = req.body;

    if (!text) {
      return res.status(400).json({ error: 'Text is required' });
    }

    let prompt = `Summarize the following text in ${max_length} words or less:\n\n"${text}"\n\n`;
    
    switch (style) {
      case 'bullet_points':
        prompt += 'Format the summary as bullet points.';
        break;
      case 'executive':
        prompt += 'Write an executive summary suitable for business use.';
        break;
      case 'paragraph':
      default:
        prompt += 'Write a concise paragraph summary.';
        break;
    }

    // Call OpenAI API
    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'You are a professional summarization assistant. Create concise, accurate summaries according to the specified format and length.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
      max_tokens: Math.min(max_length * 2, 500),
      temperature: 0.2,
    });

    const result = completion.choices[0].message.content.trim();

    // Deduct credits
    const remainingCredits = await deductCredits(
      req.user.id,
      req.creditCost,
      'summarize',
      `Summarization: ${text.substring(0, 50)}...`
    );

    // Log usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, output_data, credits_used, success) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'summarize', text, result, req.creditCost, true]
    );

    res.json({
      success: true,
      result: result,
      credits_used: req.creditCost,
      remaining_credits: remainingCredits,
    });
  } catch (error) {
    console.error('Summarization error:', error);
    
    // Log failed usage
    await db.query(
      'INSERT INTO usage_logs (user_id, function_type, input_data, credits_used, success, error_message) VALUES ($1, $2, $3, $4, $5, $6)',
      [req.user.id, 'summarize', req.body.text, 0, false, error.message]
    );

    res.status(500).json({ error: 'Summarization failed' });
  }
});

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Unhandled error:', error);
  res.status(500).json({ error: 'Internal server error' });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down gracefully');
  await db.end();
  await redis.quit();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, shutting down gracefully');
  await db.end();
  await redis.quit();
  process.exit(0);
});

module.exports = app;

