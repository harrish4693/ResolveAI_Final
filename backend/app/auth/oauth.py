import secrets
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests

from app.config import settings
from app.users.models import User, OAuthState, OAuthAccount
from app.shared.models import UserRole

# Google endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

async def generate_oauth_login_url(db: AsyncSession) -> str:
    """Generates state, nonce, stores them in DB, and returns the Google Auth URL."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    state_token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # Store state and nonce in DB, expiring in 15 minutes
    oauth_state = OAuthState(
        state_token=state_token,
        nonce=nonce,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    db.add(oauth_state)
    await db.commit()

    # Construct authorization URL
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_token,
        "nonce": nonce,
        "access_type": "online",
        "prompt": "select_account"
    }
    
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query_string}"

async def handle_oauth_callback(db: AsyncSession, state: str, code: str) -> str:
    """
    Validates state, exchanges auth code for ID token, verifies ID token (including nonce),
    finds or creates the user, and returns a short-lived exchange code.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    # 1. Validate State
    stmt = select(OAuthState).where(OAuthState.state_token == state, OAuthState.is_used == False)
    result = await db.execute(stmt)
    oauth_state = result.scalar_one_or_none()

    if not oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
        
    expires_at = oauth_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    oauth_state.is_used = True
    await db.commit()

    # 2. Exchange code with Google
    async with httpx.AsyncClient() as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri
        })
        
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to exchange authorization code: {token_res.text}")
            
        token_data = token_res.json()
        id_token_jwt = token_data.get("id_token")
        
        if not id_token_jwt:
            raise HTTPException(status_code=400, detail="No ID token received from Google")

    # 3. Verify ID Token using google-auth library
    try:
        # Request object for google-auth to fetch Google's public certs
        request = requests.Request()
        id_info = id_token.verify_oauth2_token(
            id_token_jwt, 
            request, 
            settings.google_client_id,
            clock_skew_in_seconds=60
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID token: {str(e)}")

    # 4. Validate Claims
    if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
        raise HTTPException(status_code=400, detail="Invalid issuer")
        
    if id_info.get("nonce") != oauth_state.nonce:
        raise HTTPException(status_code=400, detail="Invalid nonce. Possible replay attack.")
        
    email = id_info.get("email")
    email_verified = id_info.get("email_verified", False)
    sub = id_info.get("sub")
    name = id_info.get("name", "Google User")
    picture = id_info.get("picture")

    if not email or not sub:
        raise HTTPException(status_code=400, detail="Missing email or subject in ID token")
        
    if not email_verified:
        raise HTTPException(status_code=400, detail="Google email is not verified")

    # 5. Find or Create User
    # First, check if OAuthAccount exists for this sub
    stmt = select(OAuthAccount).where(OAuthAccount.provider == "google", OAuthAccount.provider_subject == sub)
    result = await db.execute(stmt)
    oauth_account = result.scalar_one_or_none()
    
    user = None
    if oauth_account:
        # User is already linked
        user_res = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=500, detail="User record missing for OAuth account")
    else:
        # Check if email exists to link
        user_res = await db.execute(select(User).where(User.email == email))
        user = user_res.scalar_one_or_none()
        
        if not user:
            # Create a brand new user. Default to CUSTOMER role.
            # Use an unusable password hash
            user = User(
                email=email,
                full_name=name,
                password_hash="!oauth_only!",
                role=UserRole.CUSTOMER,
                avatar_url=picture
            )
            db.add(user)
            await db.flush() # get user.id
            
        # Link the new OAuthAccount
        new_oauth_account = OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_subject=sub
        )
        db.add(new_oauth_account)
        await db.commit()
        await db.refresh(user)

    # 6. Create Exchange Code
    exchange_code = secrets.token_urlsafe(32)
    new_state = OAuthState(
        state_token=secrets.token_urlsafe(32), # unused
        nonce="unused",
        exchange_code=exchange_code,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db.add(new_state)
    await db.commit()
    
    return exchange_code

async def exchange_oauth_code_for_user(db: AsyncSession, code: str) -> User:
    """Validates the short-lived exchange code and returns the User."""
    stmt = select(OAuthState).where(OAuthState.exchange_code == code, OAuthState.is_used == False)
    result = await db.execute(stmt)
    oauth_state = result.scalar_one_or_none()

    if not oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired exchange code")
        
    expires_at = oauth_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired exchange code")

    # Invalidate the code
    oauth_state.is_used = True
    await db.commit()

    # Get the user
    user_res = await db.execute(select(User).where(User.id == oauth_state.user_id))
    user = user_res.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="User account is inactive or missing")
        
    return user
