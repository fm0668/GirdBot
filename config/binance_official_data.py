"""
币安官方数据配置
基于币安官网公布的最新数据
更新时间: 2025/03/13 19:00
"""

from decimal import Decimal
from typing import Dict, List, Tuple


class BinanceOfficialData:
    """币安官方数据"""
    
    # DOGEUSDC永续合约杠杆分层数据
    DOGEUSDC_LEVERAGE_TIERS = [
        {
            'tier': 1,
            'min_notional': 0,
            'max_notional': 10000,
            'max_leverage': 75,
            'maintenance_margin_rate': Decimal('0.005'),    # 0.50%
            'maintenance_amount': Decimal('0')              # 0 USDC
        },
        {
            'tier': 2,
            'min_notional': 10000,
            'max_notional': 50000,
            'max_leverage': 50,
            'maintenance_margin_rate': Decimal('0.007'),    # 0.70%
            'maintenance_amount': Decimal('20')             # 20 USDC
        },
        {
            'tier': 3,
            'min_notional': 50000,
            'max_notional': 750000,
            'max_leverage': 40,
            'maintenance_margin_rate': Decimal('0.01'),     # 1.00%
            'maintenance_amount': Decimal('170')            # 170 USDC
        },
        {
            'tier': 4,
            'min_notional': 750000,
            'max_notional': 1000000,
            'max_leverage': 25,
            'maintenance_margin_rate': Decimal('0.02'),     # 2.00%
            'maintenance_amount': Decimal('7670')           # 7,670 USDC
        },
        {
            'tier': 5,
            'min_notional': 1000000,
            'max_notional': 2000000,
            'max_leverage': 20,
            'maintenance_margin_rate': Decimal('0.025'),    # 2.50%
            'maintenance_amount': Decimal('12670')          # 12,670 USDC
        },
        {
            'tier': 6,
            'min_notional': 2000000,
            'max_notional': 10000000,
            'max_leverage': 10,
            'maintenance_margin_rate': Decimal('0.05'),     # 5.00%
            'maintenance_amount': Decimal('62670')          # 62,670 USDC
        },
        {
            'tier': 7,
            'min_notional': 10000000,
            'max_notional': 20000000,
            'max_leverage': 5,
            'maintenance_margin_rate': Decimal('0.1'),      # 10.00%
            'maintenance_amount': Decimal('562670')         # 562,670 USDC
        },
        {
            'tier': 8,
            'min_notional': 20000000,
            'max_notional': 25000000,
            'max_leverage': 4,
            'maintenance_margin_rate': Decimal('0.125'),    # 12.50%
            'maintenance_amount': Decimal('1062670')        # 1,062,670 USDC
        },
        {
            'tier': 9,
            'min_notional': 25000000,
            'max_notional': 50000000,
            'max_leverage': 2,
            'maintenance_margin_rate': Decimal('0.25'),     # 25.00%
            'maintenance_amount': Decimal('4187670')        # 4,187,670 USDC
        },
        {
            'tier': 10,
            'min_notional': 50000000,
            'max_notional': 100000000,
            'max_leverage': 1,
            'maintenance_margin_rate': Decimal('0.5'),      # 50.00%
            'maintenance_amount': Decimal('16687670')       # 16,687,670 USDC
        }
    ]
    
    # USDC手续费率（普通用户）
    USDC_TRADING_FEES = {
        'maker': Decimal('0.0000'),     # 0.00%
        'taker': Decimal('0.0005')      # 0.05%
    }
    
    # USDT手续费率（普通用户）
    USDT_TRADING_FEES = {
        'maker': Decimal('0.0002'),     # 0.02%
        'taker': Decimal('0.0005')      # 0.05%
    }
    
    @classmethod
    def get_leverage_tier_for_notional(cls, symbol: str, notional_value: Decimal) -> Dict:
        """
        根据名义价值获取对应的杠杆分层
        
        Args:
            symbol: 交易对符号
            notional_value: 名义价值
        
        Returns:
            杠杆分层信息
        """
        if 'DOGE' in symbol and 'USDC' in symbol:
            tiers = cls.DOGEUSDC_LEVERAGE_TIERS
            
            for tier in tiers:
                if tier['min_notional'] <= notional_value < tier['max_notional']:
                    return tier
            
            # 如果超出最大范围，返回最后一层
            return tiers[-1]
        
        # 其他交易对使用默认值
        return {
            'tier': 1,
            'min_notional': 0,
            'max_notional': 10000,
            'max_leverage': 20,
            'maintenance_margin_rate': Decimal('0.05'),
            'maintenance_amount': Decimal('0')
        }
    
    @classmethod
    def get_trading_fees(cls, symbol: str) -> Dict[str, Decimal]:
        """
        获取交易手续费
        
        Args:
            symbol: 交易对符号
        
        Returns:
            手续费信息
        """
        if 'USDC' in symbol:
            return cls.USDC_TRADING_FEES.copy()
        else:
            return cls.USDT_TRADING_FEES.copy()
    
    @classmethod
    def calculate_maintenance_margin(cls, symbol: str, notional_value: Decimal) -> Decimal:
        """
        计算维持保证金
        
        Args:
            symbol: 交易对符号
            notional_value: 名义价值
        
        Returns:
            维持保证金金额
        """
        tier = cls.get_leverage_tier_for_notional(symbol, notional_value)
        
        # 维持保证金 = 仓位名义价值 * 维持保证金率 - 维持保证金速算额
        maintenance_margin = (notional_value * tier['maintenance_margin_rate'] - 
                            tier['maintenance_amount'])
        
        return max(maintenance_margin, Decimal('0'))  # 不能为负数
    
    @classmethod
    def get_max_leverage_for_notional(cls, symbol: str, notional_value: Decimal) -> int:
        """
        根据名义价值获取最大杠杆
        
        Args:
            symbol: 交易对符号
            notional_value: 名义价值
        
        Returns:
            最大杠杆倍数
        """
        tier = cls.get_leverage_tier_for_notional(symbol, notional_value)
        return tier['max_leverage']
    
    @classmethod
    def get_initial_margin_rate(cls, symbol: str, leverage: int) -> Decimal:
        """
        计算初始保证金率
        
        Args:
            symbol: 交易对符号
            leverage: 杠杆倍数
        
        Returns:
            初始保证金率
        """
        # 初始保证金率 = 1 / 杠杆倍数
        return Decimal('1') / Decimal(str(leverage))
    
    @classmethod
    def validate_leverage(cls, symbol: str, notional_value: Decimal, leverage: int) -> bool:
        """
        验证杠杆是否合法
        
        Args:
            symbol: 交易对符号
            notional_value: 名义价值
            leverage: 杠杆倍数
        
        Returns:
            是否合法
        """
        max_leverage = cls.get_max_leverage_for_notional(symbol, notional_value)
        return 1 <= leverage <= max_leverage


# 使用示例
if __name__ == "__main__":
    # 测试DOGEUSDC数据
    symbol = "DOGE/USDC:USDC"
    notional = Decimal("5000")  # 5000 USDC名义价值
    
    print(f"交易对: {symbol}")
    print(f"名义价值: ${notional}")
    
    # 获取杠杆分层
    tier = BinanceOfficialData.get_leverage_tier_for_notional(symbol, notional)
    print(f"杠杆分层: 第{tier['tier']}层")
    print(f"维持保证金率: {tier['maintenance_margin_rate']*100:.2f}%")
    print(f"最大杠杆: {tier['max_leverage']}x")
    
    # 获取手续费
    fees = BinanceOfficialData.get_trading_fees(symbol)
    print(f"挂单手续费: {fees['maker']*100:.2f}%")
    print(f"吃单手续费: {fees['taker']*100:.2f}%")
    
    # 计算维持保证金
    maintenance = BinanceOfficialData.calculate_maintenance_margin(symbol, notional)
    print(f"维持保证金: ${maintenance}")
    
    # 验证杠杆
    leverage = 50
    is_valid = BinanceOfficialData.validate_leverage(symbol, notional, leverage)
    print(f"杠杆{leverage}x是否合法: {is_valid}")
