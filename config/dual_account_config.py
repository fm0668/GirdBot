"""
双账户配置管理
目的：管理双账户的连接配置、权限验证和余额同步设置
"""

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv


@dataclass
class AccountConfig:
    """单个账户配置"""
    api_key: str
    secret_key: str
    testnet: bool = False
    enable_rate_limit: bool = True
    
    def validate(self) -> bool:
        """验证账户配置是否有效"""
        if not self.api_key or not self.secret_key:
            return False
        if len(self.api_key) < 10 or len(self.secret_key) < 10:
            return False
        return True


@dataclass  
class DualAccountConfig:
    """双账户配置管理"""
    account_a: AccountConfig  # 多头账户
    account_b: AccountConfig  # 空头账户
    exchange_name: str = "binance"
    trading_pair: str = ""
    base_asset: str = ""
    quote_asset: str = ""
    balance_sync_enabled: bool = True
    balance_tolerance_pct: Decimal = Decimal("0.05")
    
    @classmethod
    def load_from_env(cls) -> 'DualAccountConfig':
        """从环境变量加载配置"""
        load_dotenv()
        
        # 获取账户A配置
        account_a = AccountConfig(
            api_key=os.getenv('BINANCE_API_KEY_A', ''),
            secret_key=os.getenv('BINANCE_SECRET_KEY_A', ''),
            testnet=os.getenv('TESTNET', 'false').lower() == 'true',
            enable_rate_limit=True
        )
        
        # 获取账户B配置
        account_b = AccountConfig(
            api_key=os.getenv('BINANCE_API_KEY_B', ''),
            secret_key=os.getenv('BINANCE_SECRET_KEY_B', ''),
            testnet=os.getenv('TESTNET', 'false').lower() == 'true',
            enable_rate_limit=True
        )
        
        return cls(
            account_a=account_a,
            account_b=account_b,
            exchange_name=os.getenv('EXCHANGE_NAME', 'binance'),
            trading_pair=os.getenv('TRADING_PAIR', ''),
            base_asset=os.getenv('BASE_ASSET', ''),
            quote_asset=os.getenv('QUOTE_ASSET', ''),
            balance_sync_enabled=True,
            balance_tolerance_pct=Decimal(os.getenv('BALANCE_TOLERANCE_PCT', '0.05'))
        )
    
    def validate_config(self) -> bool:
        """验证配置完整性"""
        if not self.account_a.validate() or not self.account_b.validate():
            return False
        if not self.trading_pair or not self.base_asset or not self.quote_asset:
            return False
        if self.balance_tolerance_pct < 0 or self.balance_tolerance_pct > Decimal("0.5"):
            return False
        return True
    
    def get_account_config(self, account_type: str) -> AccountConfig:
        """获取指定账户配置"""
        if account_type.upper() == 'A' or account_type.upper() == 'LONG':
            return self.account_a
        elif account_type.upper() == 'B' or account_type.upper() == 'SHORT':
            return self.account_b
        else:
            raise ValueError(f"Invalid account type: {account_type}")
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'account_a': {
                'api_key_masked': self._mask_api_key(self.account_a.api_key),
                'testnet': self.account_a.testnet,
                'enable_rate_limit': self.account_a.enable_rate_limit
            },
            'account_b': {
                'api_key_masked': self._mask_api_key(self.account_b.api_key),
                'testnet': self.account_b.testnet,
                'enable_rate_limit': self.account_b.enable_rate_limit
            },
            'exchange_name': self.exchange_name,
            'trading_pair': self.trading_pair,
            'base_asset': self.base_asset,
            'quote_asset': self.quote_asset,
            'balance_sync_enabled': self.balance_sync_enabled,
            'balance_tolerance_pct': str(self.balance_tolerance_pct)
        }
    
    def _mask_api_key(self, api_key: str) -> str:
        """脱敏API密钥"""
        if len(api_key) <= 8:
            return "***"
        return f"{api_key[:4]}***{api_key[-4:]}"