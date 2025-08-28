#!/bin/bash
# Custom secret pattern scanner for pre-commit hook
# Scans for common secret patterns and fails fast

set -e

echo "🔍 Scanning for potential secrets in staged files..."

# Define high-risk secret patterns
declare -A PATTERNS=(
    ["Stripe API Keys"]="sk_(test_|live_)[a-zA-Z0-9]{24,}"
    ["Stripe Webhook Secrets"]="whsec_[a-zA-Z0-9]{32,}"
    ["OpenAI API Keys"]="sk-[a-zA-Z0-9]{48,}"
    ["Anthropic API Keys"]="sk-ant-[a-zA-Z0-9-]{95,}"
    ["JWT Secrets"]="jwt[_-]?secret[\"':=\s]+[\"'][a-zA-Z0-9]{20,}[\"']"
    ["Database URLs with Creds"]="postgresql://[^:\s]+:[^@\s]+@[^\s]+"
    ["AWS Access Keys"]="AKIA[0-9A-Z]{16}"
    ["Google API Keys"]="AIza[0-9A-Za-z\\-_]{35}"
    ["Generic API Keys"]="(api[_-]?key|secret[_-]?key)[\s]*[=:]\s*[\"'][a-zA-Z0-9]{20,}[\"']"
    ["Hardcoded Passwords"]="password[\s]*[=:]\s*[\"'][^\s\"']{8,}[\"']"
)

# Patterns that indicate test/example values (reduce false positives)
SAFE_PATTERNS=(
    "example"
    "test"
    "fake" 
    "dummy"
    "placeholder"
    "your[-_]"
    "changeme"
    "TODO"
    "FIXME"
    "sample"
    "template"
)

# Get list of staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|js|ts|yaml|yml|json|env)$' || true)

if [ -z "$STAGED_FILES" ]; then
    echo "No relevant staged files found"
    exit 0
fi

SECRETS_FOUND=false
TEMP_FILE=$(mktemp)

# Function to check if a line contains safe patterns
is_safe_pattern() {
    local line="$1"
    for safe_pattern in "${SAFE_PATTERNS[@]}"; do
        if echo "$line" | grep -qi "$safe_pattern"; then
            return 0  # Safe pattern found
        fi
    done
    return 1  # No safe pattern found
}

# Function to check if file should be excluded
should_exclude_file() {
    local file="$1"
    case "$file" in
        *.example|*.template|*test*|*spec*|*mock*)
            return 0 ;;
        .env.example|.secrets.baseline|*.md)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

# Scan each staged file
while IFS= read -r file; do
    if should_exclude_file "$file"; then
        continue
    fi
    
    if [ ! -f "$file" ]; then
        continue
    fi
    
    echo "Scanning: $file"
    
    # Check each pattern
    for pattern_name in "${!PATTERNS[@]}"; do
        pattern="${PATTERNS[$pattern_name]}"
        
        # Search for pattern in file
        matches=$(grep -n -E "$pattern" "$file" 2>/dev/null || true)
        
        if [ -n "$matches" ]; then
            # Filter out safe patterns
            while IFS= read -r match; do
                if [ -n "$match" ] && ! is_safe_pattern "$match"; then
                    echo "❌ POTENTIAL SECRET DETECTED"
                    echo "   Type: $pattern_name"
                    echo "   File: $file"
                    echo "   Match: $match"
                    echo "   Pattern: $pattern"
                    echo ""
                    SECRETS_FOUND=true
                    echo "$file:$match" >> "$TEMP_FILE"
                fi
            done <<< "$matches"
        fi
    done
    
done <<< "$STAGED_FILES"

# Additional checks for specific high-risk scenarios
echo "🔍 Running additional security checks..."

# Check for .env files being committed (should usually be ignored)
ENV_FILES=$(echo "$STAGED_FILES" | grep -E '\.env$' || true)
if [ -n "$ENV_FILES" ]; then
    echo "⚠️ WARNING: .env files are being committed:"
    echo "$ENV_FILES"
    echo "Consider adding .env to .gitignore if it contains secrets"
    echo ""
fi

# Check for hardcoded localhost database connections in non-example files
LOCALHOST_DB=$(echo "$STAGED_FILES" | xargs grep -l "localhost.*postgres\|127\.0\.0\.1.*postgres" 2>/dev/null | grep -v example || true)
if [ -n "$LOCALHOST_DB" ]; then
    echo "⚠️ WARNING: Hardcoded localhost database connections found:"
    echo "$LOCALHOST_DB"
    echo "Consider using environment variables instead"
    echo ""
fi

# Check for TODO/FIXME comments about security
TODO_SECURITY=$(echo "$STAGED_FILES" | xargs grep -n -i "TODO.*\(security\|secret\|password\|key\)\|FIXME.*\(security\|secret\|password\|key\)" 2>/dev/null || true)
if [ -n "$TODO_SECURITY" ]; then
    echo "ℹ️ Security-related TODOs found (review before deployment):"
    echo "$TODO_SECURITY"
    echo ""
fi

# Clean up
rm -f "$TEMP_FILE"

if [ "$SECRETS_FOUND" = true ]; then
    echo ""
    echo "💥 SECRET SCAN FAILED"
    echo ""
    echo "Potential secrets or credentials were detected in your staged files."
    echo ""
    echo "🛠️ FIXES:"
    echo "1. Remove any real credentials from the code"
    echo "2. Use environment variables instead (see .env.example)"
    echo "3. If this is a false positive, add the pattern to .secrets.baseline:"
    echo "   detect-secrets scan --update .secrets.baseline"
    echo ""
    echo "4. For test data, ensure it contains 'test', 'fake', 'example' keywords"
    echo ""
    exit 1
else
    echo "✅ Secret scan passed - no potential secrets detected"
    exit 0
fi