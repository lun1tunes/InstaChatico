# Instagram Access Token Setup Guide

## Current Issue
Your Instagram access token is returning: `Invalid OAuth access token - Cannot parse access token`

## Solution Steps

### 1. Check Token Requirements
Based on Instagram documentation, your token needs:
- **Valid format**: Should start with `IGAA` or similar
- **Required permissions**: `instagram_basic`, `instagram_manage_comments`, `pages_show_list`, `page_read_engagement`
- **Not expired**: Tokens have limited lifespans
- **Correct app**: Must be from the Instagram app you're using

### 2. Generate New Access Token

#### Option A: Using Instagram Basic Display API
1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Create/select your Instagram app
3. Go to "Instagram Basic Display" → "Basic Display"
4. Generate a new access token with required permissions

#### Option B: Using Instagram Graph API
1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Create/select your Instagram app
3. Go to "Instagram Graph API" → "Instagram Business Account"
4. Generate a new access token

### 3. Required Permissions
Make sure your token has these permissions:
- `instagram_basic`
- `instagram_manage_comments`
- `pages_show_list`
- `page_read_engagement`

### 4. Test Token Validity
Use this endpoint to test your token:
```bash
curl "https://graph.facebook.com/v18.0/debug_token?input_token=YOUR_TOKEN&access_token=YOUR_TOKEN"
```

### 5. Update Environment Variable
```bash
export INSTA_TOKEN="your_new_valid_token"
```

### 6. Restart Services
```bash
docker-compose up -d api celery_worker
```

## Common Issues

### Issue 1: Token Format
- ❌ Wrong: `EAABwzLixnjY...` (Facebook token)
- ✅ Correct: `IGAA...` (Instagram token)

### Issue 2: Missing Permissions
- Make sure your app has all required permissions
- Check that the token was generated with the right scope

### Issue 3: Expired Token
- Instagram tokens expire after 60 days
- Generate a new token if yours is expired

### Issue 4: Wrong App
- Token must be from the Instagram app you're using
- Check that the app ID matches

## Testing Commands

### Test Token Validation
```bash
curl -s "http://localhost:4291/api/v1/instagram-replies/validate-token"
```

### Test Page Info
```bash
curl -s "http://localhost:4291/api/v1/instagram-replies/page-info"
```

### Test Manual Reply
```bash
curl -X POST "http://localhost:4291/api/v1/instagram-replies/send/test_comment_id"
```

## Debug Information

The system is working correctly:
- ✅ OAuth token is properly included in URL
- ✅ Request format is correct
- ✅ API endpoint is correct
- ✅ Error handling is working

The only issue is the access token itself.
