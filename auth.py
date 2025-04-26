from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import hashlib
import json
import os

# 加载用户配置
def load_users_config():
    config_path = os.path.join(os.path.dirname(__file__), 'users.json')
    with open(config_path, 'r') as f:
        return json.load(f)

# 获取配置
USERS_CONFIG = load_users_config()
JWT_SETTINGS = USERS_CONFIG['jwt_settings']
USERS = {user['username']: user for user in USERS_CONFIG['users']}

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_password_hash(password: str) -> str:
    """使用 PBKDF2-SHA256 生成密码哈希"""
    salt = "gpu_management_salt"  # 在生产环境中应该为每个用户使用唯一的salt
    key = hashlib.pbkdf2_hmac(
        'sha256',  # 使用的哈希算法
        password.encode(),  # 要加密的密码
        salt.encode(),  # salt值
        100000,  # 迭代次数
        dklen=64  # 密钥长度
    )
    return key.hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return get_password_hash(plain_password) == hashed_password

def authenticate_user(username: str, password: str):
    """验证用户"""
    if username not in USERS:
        return False
    user = USERS[username]
    stored_password = user.get('hashed_password', get_password_hash(user['password']))
    if not verify_password(password, stored_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, 
        JWT_SETTINGS['secret_key'], 
        algorithm=JWT_SETTINGS['algorithm']
    )
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, 
            JWT_SETTINGS['secret_key'], 
            algorithms=[JWT_SETTINGS['algorithm']]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = USERS.get(username)
    if user is None:
        raise credentials_exception
    return user

# 初始化：确保管理员密码已经哈希化
for username, user in USERS.items():
    if 'hashed_password' not in user:
        user['hashed_password'] = get_password_hash(user['password']) 