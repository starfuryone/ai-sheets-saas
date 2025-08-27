/**
 * SaaS AI Functions for Google Sheets
 * Main Apps Script file containing custom functions and API integration
 */

// Configuration
const CONFIG = {
  API_BASE_URL: 'https://your-api-domain.com/api',
  SIDEBAR_HTML_FILE: 'sidebar',
  CACHE_DURATION: 300, // 5 minutes
  MAX_RETRIES: 3
};

// Global variables for caching
let userCredits = null;
let lastCreditCheck = null;

/**
 * Custom function for AI-powered data cleaning
 * @param {string|Array} data The data to clean
 * @param {Object} options Cleaning options (optional)
 * @return {string|Array} Cleaned data
 * @customfunction
 */
function GPT_CLEAN(data, options = {}) {
  try {
    // Validate input
    if (!data || data === '') {
      return 'Error: No data provided';
    }

    // Handle array inputs (ranges)
    if (Array.isArray(data)) {
      return data.map(row => {
        if (Array.isArray(row)) {
          return row.map(cell => processCleanFunction(cell, options));
        }
        return processCleanFunction(row, options);
      });
    }

    return processCleanFunction(data, options);
  } catch (error) {
    console.error('GPT_CLEAN error:', error);
    return `Error: ${error.message}`;
  }
}

/**
 * Custom function for SEO utilities
 * @param {string} content The content to process
 * @param {string} seoType Type of SEO operation ('keywords', 'meta_description', 'ad_copy')
 * @param {Array} targetKeywords Target keywords (optional)
 * @return {string} SEO-optimized content
 * @customfunction
 */
function GPT_SEO(content, seoType = 'keywords', targetKeywords = []) {
  try {
    if (!content || content === '') {
      return 'Error: No content provided';
    }

    const validTypes = ['keywords', 'meta_description', 'ad_copy'];
    if (!validTypes.includes(seoType)) {
      return `Error: Invalid SEO type. Use: ${validTypes.join(', ')}`;
    }

    return processSeoFunction(content, seoType, targetKeywords);
  } catch (error) {
    console.error('GPT_SEO error:', error);
    return `Error: ${error.message}`;
  }
}

/**
 * Custom function for text summarization
 * @param {string|Array} text The text to summarize
 * @param {number} maxLength Maximum length of summary (optional)
 * @param {string} style Summary style ('paragraph', 'bullet_points', 'executive')
 * @return {string} Summarized text
 * @customfunction
 */
function GPT_SUMMARIZE(text, maxLength = 150, style = 'paragraph') {
  try {
    if (!text || text === '') {
      return 'Error: No text provided';
    }

    // Handle array inputs (ranges)
    let textContent = text;
    if (Array.isArray(text)) {
      textContent = text.flat().filter(cell => cell && cell !== '').join(' ');
    }

    const validStyles = ['paragraph', 'bullet_points', 'executive'];
    if (!validStyles.includes(style)) {
      return `Error: Invalid style. Use: ${validStyles.join(', ')}`;
    }

    return processSummarizeFunction(textContent, maxLength, style);
  } catch (error) {
    console.error('GPT_SUMMARIZE error:', error);
    return `Error: ${error.message}`;
  }
}

/**
 * Process data cleaning function
 */
function processCleanFunction(data, options) {
  const user = getCurrentUser();
  if (!user) {
    return 'Error: Authentication required';
  }

  // Check credits before processing
  if (!hasAvailableCredits()) {
    return 'Error: Insufficient credits';
  }

  const payload = {
    data: data.toString(),
    options: {
      strip_formatting: options.stripFormatting || true,
      normalize_case: options.normalizeCase || 'none',
      remove_duplicates: options.removeDuplicates || false
    }
  };

  const response = makeApiRequest('POST', '/functions/clean', payload);
  
  if (response.success) {
    updateCreditsCache(response.remaining_credits);
    updateSidebar();
    return response.result;
  } else {
    return `Error: ${response.error || 'Processing failed'}`;
  }
}

/**
 * Process SEO function
 */
function processSeoFunction(content, seoType, targetKeywords) {
  const user = getCurrentUser();
  if (!user) {
    return 'Error: Authentication required';
  }

  if (!hasAvailableCredits()) {
    return 'Error: Insufficient credits';
  }

  const payload = {
    content: content.toString(),
    seo_type: seoType,
    target_keywords: Array.isArray(targetKeywords) ? targetKeywords : [targetKeywords].filter(k => k),
    max_length: seoType === 'meta_description' ? 160 : 500
  };

  const response = makeApiRequest('POST', '/functions/seo', payload);
  
  if (response.success) {
    updateCreditsCache(response.remaining_credits);
    updateSidebar();
    return response.result;
  } else {
    return `Error: ${response.error || 'Processing failed'}`;
  }
}

/**
 * Process summarization function
 */
function processSummarizeFunction(text, maxLength, style) {
  const user = getCurrentUser();
  if (!user) {
    return 'Error: Authentication required';
  }

  if (!hasAvailableCredits()) {
    return 'Error: Insufficient credits';
  }

  const payload = {
    text: text.toString(),
    max_length: maxLength,
    style: style
  };

  const response = makeApiRequest('POST', '/functions/summarize', payload);
  
  if (response.success) {
    updateCreditsCache(response.remaining_credits);
    updateSidebar();
    return response.result;
  } else {
    return `Error: ${response.error || 'Processing failed'}`;
  }
}

/**
 * Get current authenticated user
 */
function getCurrentUser() {
  try {
    const user = Session.getActiveUser();
    if (!user || !user.getEmail()) {
      return null;
    }
    return user;
  } catch (error) {
    console.error('Error getting current user:', error);
    return null;
  }
}

/**
 * Check if user has available credits
 */
function hasAvailableCredits() {
  const credits = getUserCredits();
  return credits && credits.available_credits > 0;
}

/**
 * Get user credits with caching
 */
function getUserCredits() {
  const now = new Date().getTime();
  
  // Return cached credits if still valid
  if (userCredits && lastCreditCheck && (now - lastCreditCheck) < (CONFIG.CACHE_DURATION * 1000)) {
    return userCredits;
  }

  // Fetch fresh credits
  try {
    const response = makeApiRequest('GET', '/credits/balance');
    if (response.success) {
      userCredits = response;
      lastCreditCheck = now;
      return userCredits;
    }
  } catch (error) {
    console.error('Error fetching credits:', error);
  }

  return null;
}

/**
 * Update credits cache
 */
function updateCreditsCache(remainingCredits) {
  if (userCredits) {
    userCredits.available_credits = remainingCredits;
    lastCreditCheck = new Date().getTime();
  }
}

/**
 * Make API request with authentication and error handling
 */
function makeApiRequest(method, endpoint, payload = null) {
  const user = getCurrentUser();
  if (!user) {
    throw new Error('Authentication required');
  }

  const url = CONFIG.API_BASE_URL + endpoint;
  const options = {
    method: method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getOrCreateUserToken()}`,
      'X-User-Email': user.getEmail()
    },
    muteHttpExceptions: true
  };

  if (payload && (method === 'POST' || method === 'PUT')) {
    options.payload = JSON.stringify(payload);
  }

  let lastError = null;
  
  // Retry logic
  for (let attempt = 1; attempt <= CONFIG.MAX_RETRIES; attempt++) {
    try {
      const response = UrlFetchApp.fetch(url, options);
      const responseCode = response.getResponseCode();
      const responseText = response.getContentText();

      if (responseCode >= 200 && responseCode < 300) {
        return JSON.parse(responseText);
      } else if (responseCode === 401) {
        // Token expired, refresh and retry
        refreshUserToken();
        options.headers['Authorization'] = `Bearer ${getOrCreateUserToken()}`;
        continue;
      } else {
        const errorData = JSON.parse(responseText);
        lastError = new Error(errorData.error || `HTTP ${responseCode}`);
      }
    } catch (error) {
      lastError = error;
      console.error(`API request attempt ${attempt} failed:`, error);
      
      if (attempt < CONFIG.MAX_RETRIES) {
        Utilities.sleep(1000 * attempt); // Exponential backoff
      }
    }
  }

  throw lastError || new Error('API request failed after retries');
}

/**
 * Get or create user authentication token
 */
function getOrCreateUserToken() {
  const cache = CacheService.getUserCache();
  let token = cache.get('auth_token');

  if (!token) {
    token = refreshUserToken();
  }

  return token;
}

/**
 * Refresh user authentication token
 */
function refreshUserToken() {
  const user = getCurrentUser();
  if (!user) {
    throw new Error('No authenticated user');
  }

  try {
    // Get Google OAuth token
    const googleToken = ScriptApp.getOAuthToken();
    
    const response = UrlFetchApp.fetch(`${CONFIG.API_BASE_URL}/auth/google`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      payload: JSON.stringify({
        google_token: googleToken,
        sheets_access_token: googleToken
      }),
      muteHttpExceptions: true
    });

    if (response.getResponseCode() === 200) {
      const data = JSON.parse(response.getContentText());
      const token = data.jwt_token;
      
      // Cache token for 1 hour
      const cache = CacheService.getUserCache();
      cache.put('auth_token', token, 3600);
      
      return token;
    } else {
      throw new Error('Authentication failed');
    }
  } catch (error) {
    console.error('Token refresh failed:', error);
    throw error;
  }
}

/**
 * Show sidebar UI
 */
function showSidebar() {
  const html = HtmlService.createTemplateFromFile(CONFIG.SIDEBAR_HTML_FILE);
  const htmlOutput = html.evaluate()
    .setTitle('AI Functions')
    .setWidth(300);
  
  SpreadsheetApp.getUi().showSidebar(htmlOutput);
}

/**
 * Update sidebar with current data
 */
function updateSidebar() {
  // This will be called from the sidebar JavaScript
  // to refresh the display with current credit information
}

/**
 * Get user data for sidebar
 */
function getSidebarData() {
  const user = getCurrentUser();
  const credits = getUserCredits();
  
  return {
    user: {
      email: user ? user.getEmail() : null,
      name: user ? user.getUsername() : null
    },
    credits: credits || {
      total_credits: 0,
      used_credits: 0,
      available_credits: 0,
      usage_this_month: 0,
      subscription_tier: 'free'
    }
  };
}

/**
 * Menu functions
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('AI Functions')
    .addItem('Show Sidebar', 'showSidebar')
    .addItem('Refresh Credits', 'refreshCredits')
    .addSeparator()
    .addItem('Help', 'showHelp')
    .addToUi();
}

function refreshCredits() {
  userCredits = null;
  lastCreditCheck = null;
  getUserCredits();
  SpreadsheetApp.getActiveSpreadsheet().toast('Credits refreshed!', 'AI Functions');
}

function showHelp() {
  const html = HtmlService.createHtmlOutput(`
    <div style="font-family: Arial, sans-serif; padding: 20px;">
      <h2>AI Functions Help</h2>
      <h3>Available Functions:</h3>
      <ul>
        <li><strong>=GPT_CLEAN(data, options)</strong> - Clean and normalize data</li>
        <li><strong>=GPT_SEO(content, type, keywords)</strong> - SEO optimization</li>
        <li><strong>=GPT_SUMMARIZE(text, length, style)</strong> - Text summarization</li>
      </ul>
      <h3>Examples:</h3>
      <ul>
        <li>=GPT_CLEAN(A1) - Clean data in cell A1</li>
        <li>=GPT_SEO(B1, "keywords") - Extract keywords from B1</li>
        <li>=GPT_SUMMARIZE(C1:C10, 100) - Summarize range in 100 words</li>
      </ul>
    </div>
  `)
    .setWidth(400)
    .setHeight(300);
  
  SpreadsheetApp.getUi().showModalDialog(html, 'AI Functions Help');
}

