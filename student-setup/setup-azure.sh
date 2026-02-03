#!/bin/bash
# =============================================================================
# DBA5115 - Azure AI Foundry Setup Script
# =============================================================================
#
# INSTRUCTIONS FOR STUDENTS:
# 1. Open Azure Cloud Shell: https://shell.azure.com
# 2. Make sure you're using Bash (not PowerShell)
# 3. Copy and paste this ENTIRE script into the Cloud Shell
# 4. When prompted, enter your Student ID (e.g., A0123456X)
# 5. Copy the JSON output and send it to your instructor
#
# OPTIONS:
#   --cleanup    Delete all resources created by this script
#   --dry-run    Show what would be created without making changes
#
# =============================================================================

set -e  # Exit on error

# Parse command line arguments
CLEANUP_MODE=false
DRY_RUN_MODE=false
for arg in "$@"; do
    case $arg in
        --cleanup)
            CLEANUP_MODE=true
            ;;
        --dry-run)
            DRY_RUN_MODE=true
            ;;
    esac
done

echo "=============================================="
echo "DBA5115 - Azure AI Foundry Setup"
echo "=============================================="
echo ""

# Prompt for Student ID
read -p "Enter your Student ID (e.g., A0123456X): " STUDENT_ID

# Validate input - not empty
if [ -z "$STUDENT_ID" ]; then
    echo "❌ Error: Student ID cannot be empty"
    exit 1
fi

# Convert to lowercase for resource naming
STUDENT_ID_LOWER=$(echo "$STUDENT_ID" | tr '[:upper:]' '[:lower:]')

# Configuration
COURSE_CODE="dba5115"
RESOURCE_GROUP="${COURSE_CODE}-rg-${STUDENT_ID_LOWER}"
LOCATION="southeastasia"
SP_NAME="${COURSE_CODE}-sp-${STUDENT_ID_LOWER}"

echo ""
echo "📋 Configuration:"
echo "   Student ID:        $STUDENT_ID"
echo "   Resource Group:    $RESOURCE_GROUP"
echo "   Location:          $LOCATION"
echo "   Service Principal: $SP_NAME"
echo ""

# Get subscription info
SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv 2>/dev/null)
TENANT_ID=$(az account show --query tenantId -o tsv 2>/dev/null)

if [ -z "$SUBSCRIPTION_ID" ]; then
    echo "❌ Error: Not logged in to Azure CLI"
    echo "   Please run 'az login' first"
    exit 1
fi

echo "📍 Using subscription: $SUBSCRIPTION_NAME"
echo "   Subscription ID:   $SUBSCRIPTION_ID"
echo ""

# =============================================================================
# CLEANUP MODE
# =============================================================================
if [ "$CLEANUP_MODE" = true ]; then
    echo "🗑️  CLEANUP MODE"
    echo "   This will delete:"
    echo "     - Resource group: $RESOURCE_GROUP (and all resources inside)"
    echo "     - Service principal: $SP_NAME"
    echo ""
    read -p "Are you sure? This cannot be undone! (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cleanup cancelled."
        exit 0
    fi

    echo ""
    echo "🔨 Deleting service principal..."
    EXISTING_SP=$(az ad sp list --display-name "$SP_NAME" --query "[0].id" -o tsv 2>/dev/null)
    if [ -n "$EXISTING_SP" ]; then
        az ad sp delete --id "$EXISTING_SP" --only-show-errors
        echo "   ✅ Service principal deleted"
    else
        echo "   ℹ️  Service principal not found (already deleted?)"
    fi

    echo ""
    echo "🔨 Deleting resource group..."
    if az group exists --name "$RESOURCE_GROUP" 2>/dev/null | grep -q "true"; then
        az group delete --name "$RESOURCE_GROUP" --yes --no-wait --only-show-errors
        echo "   ✅ Resource group deletion started (runs in background)"
    else
        echo "   ℹ️  Resource group not found (already deleted?)"
    fi

    echo ""
    echo "✅ Cleanup initiated!"
    echo "   Note: Resource group deletion may take several minutes to complete."
    exit 0
fi

# =============================================================================
# DRY RUN MODE
# =============================================================================
if [ "$DRY_RUN_MODE" = true ]; then
    echo "🔍 DRY RUN MODE - No changes will be made"
    echo ""
    echo "Would create:"
    echo "  📁 Resource Group: $RESOURCE_GROUP"
    echo "  🔑 Service Principal: $SP_NAME"
    echo ""
    echo "Would assign these roles:"
    echo "  1.  Contributor (RG scope)"
    echo "  2.  User Access Administrator (RG scope)"
    echo "  3.  Cognitive Services Contributor (Subscription scope)"
    echo "  4.  Azure AI User (RG scope)"
    echo "  5.  Cognitive Services OpenAI User (RG scope)"
    echo "  6.  Search Service Contributor (RG scope)"
    echo "  7.  Search Index Data Reader (RG scope)"
    echo "  8.  Search Index Data Contributor (RG scope)"
    echo "  9.  Storage Blob Data Contributor (RG scope)"
    echo "  10. Azure Service Bus Data Owner (RG scope)"
    echo "  11. Cosmos DB Operator (RG scope)"
    echo "  12. Website Contributor (RG scope)"
    echo ""
    echo "Would register these resource providers:"
    echo "  - Microsoft.CognitiveServices"
    echo "  - Microsoft.Storage"
    echo "  - Microsoft.DocumentDB"
    echo "  - Microsoft.Search"
    echo "  - Microsoft.Sql"
    echo "  - Microsoft.ServiceBus"
    echo "  - Microsoft.Web"
    echo ""
    echo "Run without --dry-run to execute."
    exit 0
fi

# Confirm before proceeding
read -p "Continue with setup? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Setup cancelled."
    exit 0
fi

# =============================================================================
# STEP 1: Create Resource Group
# =============================================================================
echo ""
echo "🔨 Step 1/6: Creating resource group..."

# Check if RG already exists
if az group exists --name "$RESOURCE_GROUP" 2>/dev/null | grep -q "true"; then
    echo "   ℹ️  Resource group already exists, reusing: $RESOURCE_GROUP"
else
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --only-show-errors \
        --output none
    echo "   ✅ Resource group created: $RESOURCE_GROUP"
fi

# =============================================================================
# STEP 2: Create or Reuse Service Principal
# =============================================================================
echo ""
echo "🔨 Step 2/6: Creating service principal..."

RG_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
SUB_SCOPE="/subscriptions/$SUBSCRIPTION_ID"

# Check if SP already exists
EXISTING_SP=$(az ad sp list --display-name "$SP_NAME" --query "[0].appId" -o tsv 2>/dev/null)

if [ -n "$EXISTING_SP" ]; then
    echo "   ℹ️  Service principal already exists, reusing: $SP_NAME"
    CLIENT_ID="$EXISTING_SP"

    # Reset credentials to get a new secret
    echo "   🔄 Resetting credentials..."
    SP_OUTPUT=$(az ad sp credential reset \
        --id "$CLIENT_ID" \
        --only-show-errors \
        --output json)
    CLIENT_SECRET=$(echo "$SP_OUTPUT" | jq -r '.password')
    echo "   ✅ New credentials generated"
else
    # Create SP without role assignment (more reliable)
    SP_OUTPUT=$(az ad sp create-for-rbac \
        --name "$SP_NAME" \
        --skip-assignment \
        --only-show-errors \
        --output json)

    # Extract values from SP output
    CLIENT_ID=$(echo "$SP_OUTPUT" | jq -r '.appId')
    CLIENT_SECRET=$(echo "$SP_OUTPUT" | jq -r '.password')

    echo "   ✅ Service principal created: $SP_NAME"
fi

echo "   ℹ️  Waiting 15 seconds for service principal to propagate..."
sleep 15

# =============================================================================
# STEP 3: Assign Roles
# =============================================================================
echo ""
echo "🔨 Step 3/6: Assigning roles..."

# Track failed role assignments
FAILED_ROLES=()
ASSIGNED_COUNT=0

# Helper function to assign a role with retry
assign_role() {
    local role="$1"
    local scope="$2"
    local description="$3"
    local max_retries=3
    local retry=0

    echo -n "   Adding: $role... "

    while [ $retry -lt $max_retries ]; do
        if az role assignment create \
            --assignee "$CLIENT_ID" \
            --role "$role" \
            --scope "$scope" \
            --only-show-errors \
            --output none 2>/dev/null; then
            echo "✅"
            ASSIGNED_COUNT=$((ASSIGNED_COUNT + 1))
            return 0
        fi
        retry=$((retry + 1))
        if [ $retry -lt $max_retries ]; then
            sleep 5
        fi
    done

    echo "❌"
    FAILED_ROLES+=("$role")
    return 1
}

# Core roles (RG scope)
assign_role "Contributor" "$RG_SCOPE" "Resource management"
assign_role "User Access Administrator" "$RG_SCOPE" "Role assignments"

# Cognitive Services (Subscription scope for purge capability)
assign_role "Cognitive Services Contributor" "$SUB_SCOPE" "AI Foundry management"

# AI Services (RG scope)
assign_role "Azure AI User" "$RG_SCOPE" "AI Foundry agents data plane"
assign_role "Cognitive Services OpenAI User" "$RG_SCOPE" "OpenAI access"

# Search (RG scope)
assign_role "Search Service Contributor" "$RG_SCOPE" "Search service management"
assign_role "Search Index Data Reader" "$RG_SCOPE" "Search data read"
assign_role "Search Index Data Contributor" "$RG_SCOPE" "Search data write"

# Storage (RG scope)
assign_role "Storage Blob Data Contributor" "$RG_SCOPE" "Blob storage access"

# Service Bus (RG scope)
assign_role "Azure Service Bus Data Owner" "$RG_SCOPE" "Service Bus messaging"

# Cosmos DB (RG scope)
assign_role "Cosmos DB Operator" "$RG_SCOPE" "Cosmos DB management"

# Function Apps (RG scope)
assign_role "Website Contributor" "$RG_SCOPE" "Function App deployment"

echo ""
echo "   ℹ️  Note: Cosmos DB data plane access (Built-in Data Contributor)"
echo "      will be assigned per-account during provisioning."

# =============================================================================
# STEP 4: Register Resource Providers
# =============================================================================
echo ""
echo "🔨 Step 4/6: Registering resource providers..."

PROVIDERS=(
    "Microsoft.CognitiveServices"
    "Microsoft.Storage"
    "Microsoft.DocumentDB"
    "Microsoft.Search"
    "Microsoft.Sql"
    "Microsoft.ServiceBus"
    "Microsoft.Web"
)

for provider in "${PROVIDERS[@]}"; do
    echo -n "   Registering $provider... "
    az provider register --namespace "$provider" --only-show-errors --output none
    echo "✅"
done

# =============================================================================
# STEP 5: Wait for Critical Providers
# =============================================================================
echo ""
echo "🔨 Step 5/6: Waiting for critical providers..."

CRITICAL_PROVIDERS=("Microsoft.Sql" "Microsoft.ServiceBus" "Microsoft.Web")

for provider in "${CRITICAL_PROVIDERS[@]}"; do
    echo -n "   Checking $provider... "
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null)
        if [ "$state" = "Registered" ]; then
            echo "✅"
            break
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    if [ $attempt -eq $max_attempts ]; then
        echo "⚠️  (still registering)"
    fi
done

# =============================================================================
# STEP 6: Verification
# =============================================================================
echo ""
echo "🔨 Step 6/6: Verifying setup..."
echo "   Waiting 10 seconds for role propagation..."
sleep 10

ROLE_COUNT=$(az role assignment list --assignee "$CLIENT_ID" --subscription "$SUBSCRIPTION_ID" --query "length([])" -o tsv 2>/dev/null)

echo ""
echo "=============================================="
if [ ${#FAILED_ROLES[@]} -eq 0 ]; then
    echo "✅ SETUP COMPLETE!"
    echo "=============================================="
    echo "   Total roles assigned: $ROLE_COUNT"
else
    echo "⚠️  SETUP COMPLETED WITH WARNINGS"
    echo "=============================================="
    echo "   Roles assigned: $ASSIGNED_COUNT"
    echo "   Roles failed:   ${#FAILED_ROLES[@]}"
    echo ""
    echo "   Failed roles:"
    for role in "${FAILED_ROLES[@]}"; do
        echo "     - $role"
    done
    echo ""
    echo "   Please contact your instructor to manually assign"
    echo "   the missing roles."
    echo ""
    echo "   Service Principal ID: $CLIENT_ID"
    echo "   Resource Group: $RESOURCE_GROUP"
fi

# =============================================================================
# OUTPUT CREDENTIALS
# =============================================================================

# Save credentials to file
OUTPUT_FILE="${COURSE_CODE}-credentials-${STUDENT_ID_LOWER}.json"
cat << EOF > "$OUTPUT_FILE"
{
    "studentId": "$STUDENT_ID",
    "subscriptionId": "$SUBSCRIPTION_ID",
    "tenantId": "$TENANT_ID",
    "clientId": "$CLIENT_ID",
    "clientSecret": "$CLIENT_SECRET",
    "resourceGroup": "$RESOURCE_GROUP",
    "location": "$LOCATION"
}
EOF

echo ""
echo "💾 Credentials saved to: $OUTPUT_FILE"
echo ""
echo "📧 TO SEND TO YOUR INSTRUCTOR:"
echo ""
echo "   Option 1: Download the file"
echo "   Click the Upload/Download button in Cloud Shell toolbar,"
echo "   select 'Download', and enter: $OUTPUT_FILE"
echo ""
echo "   Option 2: Copy from below"
echo ""
echo "---------- START COPYING BELOW THIS LINE ----------"
cat "$OUTPUT_FILE"
echo "---------- STOP COPYING ABOVE THIS LINE ----------"
echo ""
echo "⚠️  IMPORTANT: Keep your clientSecret secure!"
echo "   Do not share it publicly. Only send this to your instructor."
echo ""
echo "=============================================="
