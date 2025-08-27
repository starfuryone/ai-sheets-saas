/**
 * Stripe Integration Module
 * Handles payment processing, webhooks, and subscription management
 */

const stripe = require('stripe');
const express = require('express');
const { Pool } = require('pg');
const crypto = require('crypto');

class StripeIntegration {
  constructor(stripeSecretKey, webhookSecret, database) {
    this.stripe = stripe(stripeSecretKey);
    this.webhookSecret = webhookSecret;
    this.db = database;
    this.router = express.Router();
    this.setupRoutes();
  }

  setupRoutes() {
    // Credit pack purchase
    this.router.post('/purchase/credits', this.authenticateToken.bind(this), this.createCreditPurchase.bind(this));
    
    // Subscription management
    this.router.post('/subscription/create', this.authenticateToken.bind(this), this.createSubscription.bind(this));
    this.router.post('/subscription/update', this.authenticateToken.bind(this), this.updateSubscription.bind(this));
    this.router.post('/subscription/cancel', this.authenticateToken.bind(this), this.cancelSubscription.bind(this));
    
    // Customer portal
    this.router.post('/portal/session', this.authenticateToken.bind(this), this.createPortalSession.bind(this));
    
    // Webhooks (raw body required)
    this.router.post('/webhook', express.raw({ type: 'application/json' }), this.handleWebhook.bind(this));
    
    // Payment methods
    this.router.get('/payment-methods', this.authenticateToken.bind(this), this.getPaymentMethods.bind(this));
    this.router.post('/payment-methods', this.authenticateToken.bind(this), this.addPaymentMethod.bind(this));
    this.router.delete('/payment-methods/:id', this.authenticateToken.bind(this), this.removePaymentMethod.bind(this));
  }

  // Authentication middleware (should be imported from main server)
  async authenticateToken(req, res, next) {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (!token) {
      return res.status(401).json({ error: 'Access token required' });
    }

    try {
      const jwt = require('jsonwebtoken');
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      
      const userResult = await this.db.query(
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
  }

  // Create credit pack purchase
  async createCreditPurchase(req, res) {
    try {
      const { pack_type, success_url, cancel_url } = req.body;

      // Get credit pack details
      const packResult = await this.db.query(
        'SELECT * FROM credit_packs WHERE pack_type = $1 AND is_active = true',
        [pack_type]
      );

      if (packResult.rows.length === 0) {
        return res.status(400).json({ error: 'Invalid credit pack type' });
      }

      const pack = packResult.rows[0];
      const user = req.user;

      // Get or create Stripe customer
      let customerId = user.stripe_customer_id;
      if (!customerId) {
        const customer = await this.stripe.customers.create({
          email: user.email,
          name: user.name,
          metadata: {
            user_id: user.id,
            user_email: user.email,
          },
        });
        customerId = customer.id;

        // Update user with Stripe customer ID
        await this.db.query(
          'UPDATE users SET stripe_customer_id = $1 WHERE id = $2',
          [customerId, user.id]
        );
      }

      // Create Stripe checkout session
      const session = await this.stripe.checkout.sessions.create({
        customer: customerId,
        payment_method_types: ['card'],
        line_items: [
          {
            price_data: {
              currency: 'usd',
              product_data: {
                name: pack.name,
                description: `${pack.credits.toLocaleString()} credits${pack.bonus_credits > 0 ? ` + ${pack.bonus_credits} bonus credits` : ''}`,
                images: ['https://your-domain.com/images/credits-icon.png'],
              },
              unit_amount: pack.price,
            },
            quantity: 1,
          },
        ],
        mode: 'payment',
        success_url: success_url || `${process.env.FRONTEND_URL}/purchase/success?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: cancel_url || `${process.env.FRONTEND_URL}/purchase/cancelled`,
        metadata: {
          user_id: user.id,
          pack_type: pack_type,
          credits: pack.credits.toString(),
          bonus_credits: pack.bonus_credits.toString(),
        },
      });

      res.json({
        success: true,
        checkout_url: session.url,
        session_id: session.id,
      });
    } catch (error) {
      console.error('Credit purchase error:', error);
      res.status(500).json({ error: 'Failed to create purchase session' });
    }
  }

  // Create subscription
  async createSubscription(req, res) {
    try {
      const { plan_tier, payment_method_id, billing_cycle = 'monthly' } = req.body;

      // Get subscription plan details
      const planResult = await this.db.query(
        'SELECT * FROM subscription_plans WHERE tier = $1 AND is_active = true',
        [plan_tier]
      );

      if (planResult.rows.length === 0) {
        return res.status(400).json({ error: 'Invalid subscription plan' });
      }

      const plan = planResult.rows[0];
      const user = req.user;

      // Get or create Stripe customer
      let customerId = user.stripe_customer_id;
      if (!customerId) {
        const customer = await this.stripe.customers.create({
          email: user.email,
          name: user.name,
          payment_method: payment_method_id,
          invoice_settings: {
            default_payment_method: payment_method_id,
          },
          metadata: {
            user_id: user.id,
            user_email: user.email,
          },
        });
        customerId = customer.id;

        await this.db.query(
          'UPDATE users SET stripe_customer_id = $1 WHERE id = $2',
          [customerId, user.id]
        );
      } else {
        // Attach payment method to existing customer
        await this.stripe.paymentMethods.attach(payment_method_id, {
          customer: customerId,
        });

        await this.stripe.customers.update(customerId, {
          invoice_settings: {
            default_payment_method: payment_method_id,
          },
        });
      }

      // Create or get Stripe price
      const priceAmount = billing_cycle === 'yearly' ? plan.price_yearly : plan.price_monthly;
      const interval = billing_cycle === 'yearly' ? 'year' : 'month';

      const price = await this.stripe.prices.create({
        unit_amount: priceAmount,
        currency: 'usd',
        recurring: { interval },
        product_data: {
          name: `${plan.name} Plan`,
          description: `${plan.credits_included.toLocaleString()} credits per ${interval}`,
        },
        metadata: {
          plan_tier: plan_tier,
          credits_included: plan.credits_included.toString(),
        },
      });

      // Create subscription
      const subscription = await this.stripe.subscriptions.create({
        customer: customerId,
        items: [{ price: price.id }],
        payment_behavior: 'default_incomplete',
        expand: ['latest_invoice.payment_intent'],
        metadata: {
          user_id: user.id,
          plan_tier: plan_tier,
          credits_included: plan.credits_included.toString(),
        },
      });

      // Update user subscription info
      await this.db.query(
        'UPDATE users SET subscription_tier = $1, stripe_subscription_id = $2 WHERE id = $3',
        [plan_tier, subscription.id, user.id]
      );

      res.json({
        success: true,
        subscription_id: subscription.id,
        client_secret: subscription.latest_invoice.payment_intent.client_secret,
      });
    } catch (error) {
      console.error('Subscription creation error:', error);
      res.status(500).json({ error: 'Failed to create subscription' });
    }
  }

  // Update subscription
  async updateSubscription(req, res) {
    try {
      const { new_plan_tier, billing_cycle } = req.body;
      const user = req.user;

      if (!user.stripe_subscription_id) {
        return res.status(400).json({ error: 'No active subscription found' });
      }

      // Get new plan details
      const planResult = await this.db.query(
        'SELECT * FROM subscription_plans WHERE tier = $1 AND is_active = true',
        [new_plan_tier]
      );

      if (planResult.rows.length === 0) {
        return res.status(400).json({ error: 'Invalid subscription plan' });
      }

      const plan = planResult.rows[0];
      const priceAmount = billing_cycle === 'yearly' ? plan.price_yearly : plan.price_monthly;
      const interval = billing_cycle === 'yearly' ? 'year' : 'month';

      // Create new price
      const price = await this.stripe.prices.create({
        unit_amount: priceAmount,
        currency: 'usd',
        recurring: { interval },
        product_data: {
          name: `${plan.name} Plan`,
          description: `${plan.credits_included.toLocaleString()} credits per ${interval}`,
        },
        metadata: {
          plan_tier: new_plan_tier,
          credits_included: plan.credits_included.toString(),
        },
      });

      // Update subscription
      const subscription = await this.stripe.subscriptions.retrieve(user.stripe_subscription_id);
      
      await this.stripe.subscriptions.update(user.stripe_subscription_id, {
        items: [{
          id: subscription.items.data[0].id,
          price: price.id,
        }],
        proration_behavior: 'create_prorations',
        metadata: {
          user_id: user.id,
          plan_tier: new_plan_tier,
          credits_included: plan.credits_included.toString(),
        },
      });

      // Update user subscription tier
      await this.db.query(
        'UPDATE users SET subscription_tier = $1 WHERE id = $2',
        [new_plan_tier, user.id]
      );

      res.json({
        success: true,
        message: 'Subscription updated successfully',
      });
    } catch (error) {
      console.error('Subscription update error:', error);
      res.status(500).json({ error: 'Failed to update subscription' });
    }
  }

  // Cancel subscription
  async cancelSubscription(req, res) {
    try {
      const { cancel_at_period_end = true } = req.body;
      const user = req.user;

      if (!user.stripe_subscription_id) {
        return res.status(400).json({ error: 'No active subscription found' });
      }

      if (cancel_at_period_end) {
        // Cancel at period end
        await this.stripe.subscriptions.update(user.stripe_subscription_id, {
          cancel_at_period_end: true,
        });
      } else {
        // Cancel immediately
        await this.stripe.subscriptions.cancel(user.stripe_subscription_id);
        
        // Update user subscription tier to free
        await this.db.query(
          'UPDATE users SET subscription_tier = $1, stripe_subscription_id = NULL WHERE id = $2',
          ['free', user.id]
        );
      }

      res.json({
        success: true,
        message: cancel_at_period_end ? 'Subscription will cancel at period end' : 'Subscription cancelled immediately',
      });
    } catch (error) {
      console.error('Subscription cancellation error:', error);
      res.status(500).json({ error: 'Failed to cancel subscription' });
    }
  }

  // Create customer portal session
  async createPortalSession(req, res) {
    try {
      const { return_url } = req.body;
      const user = req.user;

      if (!user.stripe_customer_id) {
        return res.status(400).json({ error: 'No Stripe customer found' });
      }

      const session = await this.stripe.billingPortal.sessions.create({
        customer: user.stripe_customer_id,
        return_url: return_url || `${process.env.FRONTEND_URL}/account`,
      });

      res.json({
        success: true,
        portal_url: session.url,
      });
    } catch (error) {
      console.error('Portal session error:', error);
      res.status(500).json({ error: 'Failed to create portal session' });
    }
  }

  // Get payment methods
  async getPaymentMethods(req, res) {
    try {
      const user = req.user;

      if (!user.stripe_customer_id) {
        return res.json({ success: true, payment_methods: [] });
      }

      const paymentMethods = await this.stripe.paymentMethods.list({
        customer: user.stripe_customer_id,
        type: 'card',
      });

      res.json({
        success: true,
        payment_methods: paymentMethods.data.map(pm => ({
          id: pm.id,
          brand: pm.card.brand,
          last4: pm.card.last4,
          exp_month: pm.card.exp_month,
          exp_year: pm.card.exp_year,
        })),
      });
    } catch (error) {
      console.error('Get payment methods error:', error);
      res.status(500).json({ error: 'Failed to retrieve payment methods' });
    }
  }

  // Add payment method
  async addPaymentMethod(req, res) {
    try {
      const { payment_method_id } = req.body;
      const user = req.user;

      if (!user.stripe_customer_id) {
        return res.status(400).json({ error: 'No Stripe customer found' });
      }

      await this.stripe.paymentMethods.attach(payment_method_id, {
        customer: user.stripe_customer_id,
      });

      res.json({
        success: true,
        message: 'Payment method added successfully',
      });
    } catch (error) {
      console.error('Add payment method error:', error);
      res.status(500).json({ error: 'Failed to add payment method' });
    }
  }

  // Remove payment method
  async removePaymentMethod(req, res) {
    try {
      const { id } = req.params;

      await this.stripe.paymentMethods.detach(id);

      res.json({
        success: true,
        message: 'Payment method removed successfully',
      });
    } catch (error) {
      console.error('Remove payment method error:', error);
      res.status(500).json({ error: 'Failed to remove payment method' });
    }
  }

  // Handle Stripe webhooks
  async handleWebhook(req, res) {
    const sig = req.headers['stripe-signature'];
    let event;

    try {
      event = this.stripe.webhooks.constructEvent(req.body, sig, this.webhookSecret);
    } catch (err) {
      console.error('Webhook signature verification failed:', err.message);
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    try {
      await this.processWebhookEvent(event);
      res.json({ received: true });
    } catch (error) {
      console.error('Webhook processing error:', error);
      res.status(500).json({ error: 'Webhook processing failed' });
    }
  }

  // Process webhook events
  async processWebhookEvent(event) {
    console.log(`Processing webhook event: ${event.type}`);

    switch (event.type) {
      case 'checkout.session.completed':
        await this.handleCheckoutCompleted(event.data.object);
        break;

      case 'invoice.payment_succeeded':
        await this.handlePaymentSucceeded(event.data.object);
        break;

      case 'invoice.payment_failed':
        await this.handlePaymentFailed(event.data.object);
        break;

      case 'customer.subscription.updated':
        await this.handleSubscriptionUpdated(event.data.object);
        break;

      case 'customer.subscription.deleted':
        await this.handleSubscriptionDeleted(event.data.object);
        break;

      case 'payment_method.attached':
        await this.handlePaymentMethodAttached(event.data.object);
        break;

      default:
        console.log(`Unhandled event type: ${event.type}`);
    }
  }

  // Handle successful checkout (credit purchases)
  async handleCheckoutCompleted(session) {
    const userId = session.metadata.user_id;
    const credits = parseInt(session.metadata.credits);
    const bonusCredits = parseInt(session.metadata.bonus_credits) || 0;
    const totalCredits = credits + bonusCredits;

    const client = await this.db.connect();
    
    try {
      await client.query('BEGIN');

      // Add credits to user account
      const updateResult = await client.query(
        'UPDATE users SET total_credits = total_credits + $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2 RETURNING total_credits, used_credits',
        [totalCredits, userId]
      );

      const user = updateResult.rows[0];
      const balanceAfter = user.total_credits - user.used_credits;

      // Log credit transaction
      await client.query(
        'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description, stripe_payment_id) VALUES ($1, $2, $3, $4, $5, $6)',
        [userId, 'purchase', totalCredits, balanceAfter, `Credit pack purchase: ${credits} credits${bonusCredits > 0 ? ` + ${bonusCredits} bonus` : ''}`, session.payment_intent]
      );

      await client.query('COMMIT');
      console.log(`Added ${totalCredits} credits to user ${userId}`);
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  // Handle successful subscription payment
  async handlePaymentSucceeded(invoice) {
    if (invoice.subscription) {
      const subscription = await this.stripe.subscriptions.retrieve(invoice.subscription);
      const userId = subscription.metadata.user_id;
      const creditsIncluded = parseInt(subscription.metadata.credits_included);

      const client = await this.db.connect();
      
      try {
        await client.query('BEGIN');

        // Add monthly/yearly credits
        const updateResult = await client.query(
          'UPDATE users SET total_credits = total_credits + $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2 RETURNING total_credits, used_credits',
          [creditsIncluded, userId]
        );

        const user = updateResult.rows[0];
        const balanceAfter = user.total_credits - user.used_credits;

        // Log credit transaction
        await client.query(
          'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description, stripe_payment_id) VALUES ($1, $2, $3, $4, $5, $6)',
          [userId, 'purchase', creditsIncluded, balanceAfter, `Subscription renewal: ${creditsIncluded} credits`, invoice.payment_intent]
        );

        await client.query('COMMIT');
        console.log(`Added ${creditsIncluded} subscription credits to user ${userId}`);
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      } finally {
        client.release();
      }
    }
  }

  // Handle failed payment
  async handlePaymentFailed(invoice) {
    if (invoice.subscription) {
      const subscription = await this.stripe.subscriptions.retrieve(invoice.subscription);
      const userId = subscription.metadata.user_id;

      // Log payment failure
      await this.db.query(
        'INSERT INTO credits (user_id, transaction_type, amount, balance_after, description, stripe_payment_id) VALUES ($1, $2, $3, $4, $5, $6)',
        [userId, 'refund', 0, 0, 'Payment failed - subscription renewal', invoice.payment_intent]
      );

      console.log(`Payment failed for user ${userId}, subscription ${invoice.subscription}`);
      
      // Here you could send an email notification or take other actions
    }
  }

  // Handle subscription updates
  async handleSubscriptionUpdated(subscription) {
    const userId = subscription.metadata.user_id;
    const planTier = subscription.metadata.plan_tier;

    if (subscription.cancel_at_period_end) {
      console.log(`Subscription ${subscription.id} will cancel at period end for user ${userId}`);
    } else {
      // Update user subscription tier
      await this.db.query(
        'UPDATE users SET subscription_tier = $1 WHERE id = $2',
        [planTier, userId]
      );
      
      console.log(`Updated subscription tier to ${planTier} for user ${userId}`);
    }
  }

  // Handle subscription deletion
  async handleSubscriptionDeleted(subscription) {
    const userId = subscription.metadata.user_id;

    // Update user to free tier
    await this.db.query(
      'UPDATE users SET subscription_tier = $1, stripe_subscription_id = NULL WHERE id = $2',
      ['free', userId]
    );

    console.log(`Subscription cancelled for user ${userId}, moved to free tier`);
  }

  // Handle payment method attachment
  async handlePaymentMethodAttached(paymentMethod) {
    console.log(`Payment method ${paymentMethod.id} attached to customer ${paymentMethod.customer}`);
  }

  // Get router for mounting in main app
  getRouter() {
    return this.router;
  }
}

module.exports = StripeIntegration;

