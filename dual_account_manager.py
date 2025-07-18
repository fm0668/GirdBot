"""
双账户管理器
专门处理双永续合约账户的余额获取和资金管理
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Tuple, Optional

from enhanced_exchange_client import EnhancedExchangeClient, create_enhanced_clients_from_env
from core_grid_calculator import CoreGridCalculator


@dataclass
class DualAccountBalance:
    """双账户余额信息"""
    long_account_balance: Decimal
    short_account_balance: Decimal
    total_balance: Decimal
    min_balance: Decimal
    max_balance: Decimal
    balance_ratio: Decimal  # 长账户/短账户余额比例
    
    def get_usable_balance_per_account(self, safety_factor: Decimal = Decimal("0.9")) -> Decimal:
        """获取每个账户的可用余额 (应用安全系数)"""
        return self.min_balance * safety_factor
    
    def is_balanced(self, tolerance: Decimal = Decimal("0.1")) -> bool:
        """检查两个账户余额是否平衡 (容差10%)"""
        if self.min_balance == 0:
            return False
        
        balance_diff_pct = abs(self.long_account_balance - self.short_account_balance) / self.min_balance
        return balance_diff_pct <= tolerance


class DualAccountManager:
    """双账户管理器"""
    
    def __init__(self, long_client: EnhancedExchangeClient, short_client: EnhancedExchangeClient):
        self.long_client = long_client
        self.short_client = short_client
        
        # 配置参数
        self.quote_asset = "USDC"  # DOGE/USDC:USDC的计价货币
        self.safety_factor = Decimal("0.9")  # 安全系数
        
    async def get_dual_account_balance(self) -> DualAccountBalance:
        """获取双账户余额信息"""
        try:
            # 并行获取两个账户的余额
            long_balance_task = self.long_client.get_balance("binance_futures", self.quote_asset)
            short_balance_task = self.short_client.get_balance("binance_futures", self.quote_asset)
            
            long_balance, short_balance = await asyncio.gather(
                long_balance_task, 
                short_balance_task
            )
            
            # 计算统计信息
            total_balance = long_balance + short_balance
            min_balance = min(long_balance, short_balance)
            max_balance = max(long_balance, short_balance)
            
            # 计算余额比例 (避免除零)
            if short_balance > 0:
                balance_ratio = long_balance / short_balance
            else:
                balance_ratio = Decimal("0")
            
            return DualAccountBalance(
                long_account_balance=long_balance,
                short_account_balance=short_balance,
                total_balance=total_balance,
                min_balance=min_balance,
                max_balance=max_balance,
                balance_ratio=balance_ratio
            )
            
        except Exception as e:
            print(f"❌ 获取双账户余额失败: {e}")
            raise
    
    async def calculate_grid_parameters_with_dual_balance(self, 
                                                        trading_pair: str = "DOGE/USDC:USDC") -> Dict:
        """基于双账户余额计算网格参数"""
        try:
            # 1. 获取双账户余额
            dual_balance = await self.get_dual_account_balance()
            
            print(f"📊 双账户余额信息:")
            print(f"   做多账户: {dual_balance.long_account_balance} {self.quote_asset}")
            print(f"   做空账户: {dual_balance.short_account_balance} {self.quote_asset}")
            print(f"   总余额: {dual_balance.total_balance} {self.quote_asset}")
            print(f"   余额比例: {dual_balance.balance_ratio:.3f}")
            print(f"   余额平衡: {'✅' if dual_balance.is_balanced() else '⚠️'}")
            
            # 2. 检查余额充足性
            min_required_balance = Decimal("100")  # 最小需要100 USDC
            if dual_balance.min_balance < min_required_balance:
                raise ValueError(f"账户余额不足，最小需要 {min_required_balance} {self.quote_asset}")
            
            # 3. 使用做多账户的客户端计算网格参数 (两个账户都是期货，可以用任一个)
            calculator = CoreGridCalculator(self.long_client)
            
            # 4. 设置计算参数
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            calculator.atr_config.length = int(os.getenv('ATR_PERIOD', '14'))
            calculator.atr_config.multiplier = Decimal(os.getenv('ATR_MULTIPLIER', '2.0'))
            calculator.target_profit_rate = Decimal(os.getenv('TARGET_PROFIT_RATE', '0.002'))
            calculator.safety_factor = Decimal(os.getenv('SAFETY_FACTOR', '0.8'))
            calculator.max_leverage = int(os.getenv('MAX_LEVERAGE', '20'))
            
            # 5. 计算网格参数
            grid_parameters = await calculator.calculate_shared_grid_params(
                connector_name="binance_futures",
                trading_pair=trading_pair
            )
            
            # 6. 调整参数以适配双账户
            # 每个账户使用最小余额的90%作为可用资金
            usable_balance_per_account = dual_balance.get_usable_balance_per_account(self.safety_factor)
            
            # 重新计算单层金额 (基于实际可用余额)
            total_nominal_value = usable_balance_per_account * grid_parameters.usable_leverage
            adjusted_amount_per_grid = (total_nominal_value / grid_parameters.grid_levels).quantize(Decimal('0.01'))
            
            # 7. 构建结果
            result = {
                'dual_balance': dual_balance,
                'grid_parameters': grid_parameters,
                'usable_balance_per_account': usable_balance_per_account,
                'adjusted_amount_per_grid': adjusted_amount_per_grid,
                'total_investment_per_account': adjusted_amount_per_grid * grid_parameters.grid_levels,
                'total_investment_both_accounts': adjusted_amount_per_grid * grid_parameters.grid_levels * 2,
                'leverage_used': grid_parameters.usable_leverage,
                'grid_count': grid_parameters.grid_levels,
                'price_range': {
                    'upper_bound': grid_parameters.upper_bound,
                    'lower_bound': grid_parameters.lower_bound,
                    'range_pct': (grid_parameters.upper_bound - grid_parameters.lower_bound) / 
                                ((grid_parameters.upper_bound + grid_parameters.lower_bound) / 2) * 100
                }
            }
            
            return result
            
        except Exception as e:
            print(f"❌ 计算网格参数失败: {e}")
            raise
    
    async def validate_account_readiness(self, trading_pair: str = "DOGE/USDC:USDC") -> Dict[str, bool]:
        """验证账户准备情况"""
        try:
            validation_results = {
                'long_account_connected': False,
                'short_account_connected': False,
                'sufficient_balance': False,
                'balanced_accounts': False,
                'trading_pair_available': False,
                'leverage_set': False
            }
            
            # 1. 检查连接状态
            validation_results['long_account_connected'] = self.long_client.is_websocket_connected()
            validation_results['short_account_connected'] = self.short_client.is_websocket_connected()
            
            # 2. 检查余额
            dual_balance = await self.get_dual_account_balance()
            validation_results['sufficient_balance'] = dual_balance.min_balance >= Decimal("100")
            validation_results['balanced_accounts'] = dual_balance.is_balanced()
            
            # 3. 检查交易对
            try:
                long_symbol_info = await self.long_client.get_symbol_info(trading_pair)
                short_symbol_info = await self.short_client.get_symbol_info(trading_pair)
                validation_results['trading_pair_available'] = True
            except Exception:
                validation_results['trading_pair_available'] = False
            
            # 4. 检查杠杆设置 (尝试设置杠杆)
            try:
                await self.long_client.set_leverage(trading_pair, 20)
                await self.short_client.set_leverage(trading_pair, 20)
                validation_results['leverage_set'] = True
            except Exception:
                validation_results['leverage_set'] = False
            
            return validation_results
            
        except Exception as e:
            print(f"❌ 验证账户准备情况失败: {e}")
            return {key: False for key in validation_results.keys()}
    
    async def get_position_summary(self, trading_pair: str = "DOGE/USDC:USDC") -> Dict:
        """获取双账户持仓摘要"""
        try:
            # 并行获取持仓信息
            long_position_task = self.long_client.get_position_info(trading_pair)
            short_position_task = self.short_client.get_position_info(trading_pair)
            
            long_position, short_position = await asyncio.gather(
                long_position_task,
                short_position_task
            )
            
            return {
                'long_account': long_position,
                'short_account': short_position,
                'total_long_position': long_position.get('long_position', Decimal("0")),
                'total_short_position': short_position.get('short_position', Decimal("0")),
                'net_position': long_position.get('long_position', Decimal("0")) - 
                               short_position.get('short_position', Decimal("0")),
                'is_hedged': abs(long_position.get('long_position', Decimal("0")) - 
                               short_position.get('short_position', Decimal("0"))) < Decimal("0.001")
            }
            
        except Exception as e:
            print(f"❌ 获取持仓摘要失败: {e}")
            raise
    
    async def close(self):
        """关闭连接"""
        await asyncio.gather(
            self.long_client.close(),
            self.short_client.close()
        )


# 便捷函数
async def create_dual_account_manager() -> DualAccountManager:
    """创建双账户管理器"""
    long_client, short_client = create_enhanced_clients_from_env()
    
    # 初始化连接
    await long_client.initialize()
    await short_client.initialize()
    
    return DualAccountManager(long_client, short_client)
