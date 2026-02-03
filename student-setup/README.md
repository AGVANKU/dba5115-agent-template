# Student Azure Setup Guide

This guide explains how to set up your Azure environment for DBA5115. You'll create a **Service Principal** that allows the course infrastructure to provision Azure resources on your behalf.

## What is a Service Principal?

A **Service Principal** is like a "robot account" in Azure. Instead of using your personal login credentials, applications and automation scripts use a Service Principal to authenticate and perform actions in Azure.

### Why do we need it?

In this course, we need to create Azure resources (AI services, databases, storage, etc.) in your Azure subscription. There are two ways to do this:

1. **Manual setup** — You create every resource yourself through the Azure Portal
2. **Automated setup** — A script creates resources for you using a Service Principal

We use option 2 because:
- It's **faster** — Resources are created in minutes, not hours
- It's **consistent** — Every student gets the same configuration
- It's **reproducible** — If something breaks, we can recreate it
- It's **educational** — You learn how enterprise automation works

### How does it work?

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Instructor    │         │ Service Principal │         │ Your Azure      │
│   Automation    │ ──────► │ (Robot Account)   │ ──────► │ Subscription    │
│   Scripts       │  uses   │ with permissions  │ creates │ & Resources     │
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

1. You create a Service Principal in your Azure subscription
2. You send the credentials to your instructor
3. The instructor's automation uses those credentials to create resources
4. Resources are created in **your** subscription — you own and control them

### Is it safe?

Yes, because:
- The Service Principal only has access to a **specific Resource Group** (a container for resources)
- It cannot access other resources in your subscription
- You can **revoke access** at any time by deleting the Service Principal
- The credentials are only shared with your instructor via secure channels

---

## Step-by-Step Setup Instructions

### Prerequisites

- An active Azure subscription (you can use Azure for Students or a free trial)
- Access to [Azure Cloud Shell](https://shell.azure.com)

### Step 1: Open Azure Cloud Shell

1. Go to [https://shell.azure.com](https://shell.azure.com)
2. Sign in with your Azure account
3. If prompted, select **Bash** (not PowerShell)

   ![Select Bash](https://docs.microsoft.com/en-us/azure/cloud-shell/media/overview/overview-bash-pic.png)

4. If this is your first time, you may be asked to create a storage account — click **Create storage**

### Step 2: Copy the Setup Script

1. Open the file `setup-azure.sh` in this folder
2. Select **all the content** of the file (Ctrl+A or Cmd+A)
3. Copy it to your clipboard (Ctrl+C or Cmd+C)

### Step 3: Paste and Run in Cloud Shell

1. In the Azure Cloud Shell terminal, **right-click** and select **Paste**
   - Or use keyboard: Ctrl+Shift+V (Windows/Linux) or Cmd+V (Mac)

2. The entire script will be pasted into the terminal

3. Press **Enter** to start execution

4. When prompted, enter your Student ID:
   ```
   Enter your Student ID (e.g., A0123456X): _
   ```

5. Review the configuration and type `y` to continue:
   ```
   Continue with setup? (y/n): y
   ```

### Step 4: Wait for Completion

The script will:
1. Create a Resource Group for your course resources
2. Create a Service Principal with necessary permissions
3. Register required Azure resource providers
4. Verify the setup

This takes approximately 2-3 minutes.

### Step 5: Send Credentials to Instructor

When the script completes, your credentials are automatically saved to a file:

```
💾 Credentials saved to: dba5115-credentials-a0123456x.json
```

You have two options to send this to your instructor:

#### Option A: Download the File (Recommended)

1. In Cloud Shell, click the **Upload/Download** button in the toolbar (looks like `↑↓`)
2. Select **Download**
3. Enter the filename: `dba5115-credentials-{your-student-id}.json`
4. The file will download to your computer
5. Send this file to your instructor via the designated channel (email, LMS, etc.)

#### Option B: Copy from Terminal

The credentials are also displayed in the terminal:

```
---------- START COPYING BELOW THIS LINE ----------
{
    "studentId": "A0123456X",
    "subscriptionId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "tenantId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "clientId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "clientSecret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "resourceGroup": "dba5115-rg-a0123456x",
    "location": "southeastasia"
}
---------- STOP COPYING ABOVE THIS LINE ----------
```

1. **Select** the JSON content between the dashed lines
2. **Copy** it (right-click → Copy, or Ctrl+Shift+C)
3. **Send** it to your instructor via the designated channel

> ⚠️ **Important:** Keep your `clientSecret` confidential. Only share this JSON with your instructor.

---

## Troubleshooting

### "Not logged in to Azure CLI"

You need to authenticate first:
```bash
az login
```

### "Failed to create service principal"

You may not have permission to create Service Principals. Contact your instructor for assistance.

### "Failed to assign role"

Some roles require elevated permissions. The script will continue and report which roles failed. Your instructor can assign them manually.

### Re-running the Script

If the script fails partway through, you can safely re-run it. The script is **idempotent** — it will reuse existing resources instead of creating duplicates.

---

## Cleanup (End of Course)

When the course ends, you can remove all created resources by running the script with `--cleanup`:

1. Open Azure Cloud Shell
2. Paste the script content
3. Add `--cleanup` at the end before pressing Enter
4. Enter your Student ID when prompted
5. Type `yes` to confirm deletion

This will delete:
- The Resource Group (and all resources inside it)
- The Service Principal

---

## Script Options

| Option | Description |
|--------|-------------|
| (none) | Normal setup — creates resources |
| `--dry-run` | Shows what would be created without making changes |
| `--cleanup` | Deletes all resources created by this script |

---

## What Gets Created?

### Resource Group
A container named `dba5115-rg-{your-student-id}` that holds all your course resources.

### Service Principal
A robot account named `dba5115-sp-{your-student-id}` with these permissions:

| Role | Scope | Purpose |
|------|-------|---------|
| Contributor | Resource Group | Create/manage resources |
| User Access Administrator | Resource Group | Assign roles to resources |
| Cognitive Services Contributor | Subscription | Manage AI services |
| Azure AI User | Resource Group | Use AI Foundry agents |
| Cognitive Services OpenAI User | Resource Group | Access OpenAI models |
| Search Service Contributor | Resource Group | Manage AI Search |
| Search Index Data Reader/Contributor | Resource Group | Read/write search indexes |
| Storage Blob Data Contributor | Resource Group | Access blob storage |
| Azure Service Bus Data Owner | Resource Group | Send/receive messages |
| Cosmos DB Operator | Resource Group | Manage Cosmos DB |
| Website Contributor | Resource Group | Deploy Function Apps |

### Resource Providers
The script registers these Azure services in your subscription:
- Microsoft.CognitiveServices (AI services)
- Microsoft.Storage (Blob storage)
- Microsoft.DocumentDB (Cosmos DB)
- Microsoft.Search (AI Search)
- Microsoft.Sql (SQL Database)
- Microsoft.ServiceBus (Message queues)
- Microsoft.Web (Function Apps)

---

## Questions?

Contact your instructor if you encounter any issues during setup.
