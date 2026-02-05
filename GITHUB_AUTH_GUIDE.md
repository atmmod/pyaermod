# GitHub Authentication Guide for Private Repository

Since GitHub no longer accepts passwords for HTTPS authentication, you'll need to use one of these methods to push to your private repository at `https://github.com/atmmod/pyaermod`.

---

## 🔐 Method 1: HTTPS with Personal Access Token (Recommended)

This is the easiest method for most users.

### Step 1: Create Personal Access Token

1. Go to GitHub → Settings → Developer settings
2. Click "Personal access tokens" → "Tokens (classic)"
3. Click "Generate new token" → "Generate new token (classic)"
4. Fill in:
   - **Note:** "PyAERMOD Development"
   - **Expiration:** 90 days (or longer)
   - **Scopes:** Check `repo` (all sub-boxes)
5. Click "Generate token"
6. **IMPORTANT:** Copy the token immediately (you won't see it again)
   - Example: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 2: Add Remote and Push

```bash
# Add remote (use HTTPS URL)
git remote add origin https://github.com/atmmod/pyaermod.git

# Push to GitHub
git push -u origin main
```

### Step 3: Enter Credentials When Prompted

```
Username: your-github-username
Password: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # Paste your PAT here
```

### Step 4: Cache Credentials (Optional)

To avoid entering the token every time:

**On Mac:**
```bash
git config --global credential.helper osxkeychain
```

**On Windows:**
```bash
git config --global credential.helper wincred
```

**On Linux:**
```bash
git config --global credential.helper cache
# Or for permanent storage:
git config --global credential.helper store
```

After setting this, the next time you push, Git will remember your token.

---

## 🔑 Method 2: SSH Keys (Most Secure)

Better for long-term use, no token expiration.

### Step 1: Check for Existing SSH Keys

```bash
ls -la ~/.ssh
# Look for: id_rsa.pub, id_ed25519.pub, or similar
```

### Step 2: Generate New SSH Key (if needed)

```bash
# Generate key
ssh-keygen -t ed25519 -C "shannon.capps@gmail.com"

# Press Enter to accept default location
# Enter passphrase (optional but recommended)

# Start SSH agent
eval "$(ssh-agent -s)"

# Add key to agent
ssh-add ~/.ssh/id_ed25519
```

### Step 3: Add SSH Key to GitHub

```bash
# Copy public key to clipboard
# On Mac:
pbcopy < ~/.ssh/id_ed25519.pub

# On Linux:
cat ~/.ssh/id_ed25519.pub
# (then copy the output manually)

# On Windows:
clip < ~/.ssh/id_ed25519.pub
```

Then:
1. Go to GitHub → Settings → SSH and GPG keys
2. Click "New SSH key"
3. Title: "PyAERMOD Dev Machine"
4. Paste your key
5. Click "Add SSH key"

### Step 4: Test Connection

```bash
ssh -T git@github.com
# Should see: "Hi username! You've successfully authenticated..."
```

### Step 5: Add Remote and Push

```bash
# Add remote (use SSH URL)
git remote add origin git@github.com:atmmod/pyaermod.git

# Push to GitHub
git push -u origin main
```

No password/token needed! 🎉

---

## 🚀 Method 3: GitHub CLI (Easiest for Multiple Repos)

The GitHub CLI handles authentication automatically.

### Step 1: Install GitHub CLI

**On Mac:**
```bash
brew install gh
```

**On Windows:**
```powershell
winget install GitHub.cli
```

**On Linux:**
```bash
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

### Step 2: Authenticate

```bash
gh auth login
```

Follow the prompts:
- What account: `GitHub.com`
- Protocol: `HTTPS` or `SSH`
- Authenticate: `Login with a web browser`
- Copy the one-time code and press Enter
- Browser opens → paste code → authorize

### Step 3: Add Remote and Push

```bash
# Add remote
gh repo set-default atmmod/pyaermod

# Or manually:
git remote add origin https://github.com/atmmod/pyaermod.git

# Push
git push -u origin main
```

GitHub CLI handles authentication automatically!

---

## 🔧 Troubleshooting

### "Authentication failed" Error

If using HTTPS:
```bash
# Remove saved credentials
git credential-cache exit  # Linux
git credential-osxkeychain erase  # Mac

# Try again with correct token
git push
```

### "Permission denied (publickey)" Error

If using SSH:
```bash
# Check SSH agent
ssh-add -l

# If empty, add key again
ssh-add ~/.ssh/id_ed25519

# Test connection
ssh -T git@github.com
```

### Already Added Wrong Remote

```bash
# Check current remote
git remote -v

# Remove it
git remote remove origin

# Add correct one
git remote add origin [correct-url]
```

---

## 📋 Quick Reference

### HTTPS URL Format
```
https://github.com/atmmod/pyaermod.git
```

### SSH URL Format
```
git@github.com:atmmod/pyaermod.git
```

### Switch from HTTPS to SSH
```bash
git remote set-url origin git@github.com:atmmod/pyaermod.git
```

### Switch from SSH to HTTPS
```bash
git remote set-url origin https://github.com/atmmod/pyaermod.git
```

---

## ✅ Recommended Setup

**For personal development:**
→ Use **SSH keys** (most secure, no expiration)

**For CI/CD or automation:**
→ Use **Personal Access Token** with minimal scopes

**For beginners:**
→ Use **GitHub CLI** (easiest to set up)

---

## 🔒 Security Best Practices

1. ✅ **Never commit tokens** to your repository
2. ✅ **Use SSH keys** for long-term development
3. ✅ **Set token expiration** to shortest needed time
4. ✅ **Use minimal scopes** on tokens (only `repo` for private repos)
5. ✅ **Revoke tokens** immediately if compromised
6. ✅ **Use different tokens** for different machines/purposes
7. ✅ **Add passphrase** to SSH keys

---

## 📝 Updated Quick Start Commands

### Option A: HTTPS with Personal Access Token

```bash
# 1. Create PAT at: https://github.com/settings/tokens

# 2. Add remote
git remote add origin https://github.com/atmmod/pyaermod.git

# 3. Push (enter username and PAT when prompted)
git push -u origin main
```

### Option B: SSH Keys

```bash
# 1. Generate and add SSH key (see steps above)

# 2. Add remote
git remote add origin git@github.com:atmmod/pyaermod.git

# 3. Push (no password needed)
git push -u origin main
```

### Option C: GitHub CLI

```bash
# 1. Install and authenticate
gh auth login

# 2. Add remote
git remote add origin https://github.com/atmmod/pyaermod.git

# 3. Push (authentication automatic)
git push -u origin main
```

---

## 🎯 My Recommendation for You

Based on your setup, I recommend:

**Primary:** SSH keys
- Most secure
- No token expiration
- One-time setup

**Backup:** GitHub CLI
- Easiest for multiple repos
- Handles auth automatically
- Great for scripting

**Steps:**
1. Generate SSH key: `ssh-keygen -t ed25519 -C "shannon.capps@gmail.com"`
2. Add to GitHub: Copy `~/.ssh/id_ed25519.pub` to GitHub settings
3. Use SSH URL: `git@github.com:atmmod/pyaermod.git`
4. Push: `git push -u origin main`

Done! ✅

---

*For more help: https://docs.github.com/en/authentication*
