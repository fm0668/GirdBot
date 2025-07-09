#!/usr/bin/env python3
"""
网格间距计算器（传统ATR方法）
支持通过配置文件调整ATR倍数参数
"""

import asyncio
import sys
import os
from decimal import Decimal
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.append('/root/GirdBot')

from src.core.atr_analyzer import ATRAnalyzer
from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig


async def calculate_grid_spacing():
    """计算网格间距（传统ATR方法）"""
    
    print("=" * 60)
    print("网格间距计算器（传统ATR方法）")
    print("=" * 60)
    
    # 初始化配置
    config = ProductionConfig()
    
    # 创建连接器（使用长账户配置）
    connector = BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    )
    
    # 创建ATR分析器
    atr_analyzer = ATRAnalyzer(period=14, multiplier=2.0)
    
    try:
        # 连接到交易所
        await connector.connect()
        print("✓ 已连接到币安交易所")
        
        # 获取交易对信息
        symbol = "DOGEUSDC"
        print(f"✓ 分析交易对: {symbol}")
        
        # 获取K线数据
        klines = await connector.get_klines(
            symbol=symbol,
            interval="1h",
            limit=64  # 14 + 50
        )
        
        if len(klines) < 14:
            print(f"❌ K线数据不足: {len(klines)} < 14")
            return
            
        print(f"✓ 获取K线数据: {len(klines)}根")
        
        # 计算ATR值
        atr_value = await atr_analyzer.calculate_atr(klines)
        print(f"✓ ATR值: {atr_value:.8f}")
        
        # 获取当前价格
        current_price = Decimal(str(klines[-1][4]))  # 收盘价
        print(f"✓ 当前价格: {current_price:.8f}")
        
        # 测试参数（从配置文件读取）
        atr_multiplier = Decimal(str(config.trading.grid_spacing_multiplier))  # 使用配置参数
        
        print("\n" + "=" * 60)
        print("网格间距计算结果（传统ATR方法）")
        print("=" * 60)
        
        # 传统ATR方法
        print("\n【传统ATR方法】")
        print(f"公式: spacing = atr_value * atr_multiplier")
        print(f"计算: {atr_value:.8f} * {atr_multiplier}")
        
        traditional_spacing = atr_value * atr_multiplier
        print(f"结果: {traditional_spacing:.8f}")
        
        # 转换为价格百分比
        traditional_percentage = (traditional_spacing / current_price) * 100
        print(f"占当前价格百分比: {traditional_percentage:.4f}%")
        
        # 配置说明
        print(f"\n【配置说明】")
        print(f"ATR倍数参数: {atr_multiplier} (可在配置文件中修改)")
        print(f"配置文件路径: config/base_config.py -> grid_spacing_multiplier")
        print(f"当前配置值: {config.trading.grid_spacing_multiplier}")
        
        # 网格层数计算
        print("\n" + "=" * 60)
        print("网格层数计算")
        print("=" * 60)
        
        # 计算ATR通道边界
        upper_bound, lower_bound, _ = await atr_analyzer.calculate_atr_channel(klines)
        price_range = upper_bound - lower_bound
        
        print(f"ATR通道上轨:       {upper_bound:.8f}")
        print(f"ATR通道下轨:       {lower_bound:.8f}")
        print(f"价格区间:           {price_range:.8f}")
        
        # 计算网格层数
        traditional_levels = int(price_range / traditional_spacing)
        print(f"传统ATR方法网格层数: {traditional_levels}")
        
        # 每格金额计算（假设总资金1000 USDC）
        print("\n" + "=" * 60)
        print("每格金额计算（假设总资金1000 USDC）")
        print("=" * 60)
        
        total_fund = Decimal("1000")
        traditional_per_grid = total_fund / traditional_levels if traditional_levels > 0 else 0
        print(f"每格金额: {traditional_per_grid:.2f} USDC")
        
        # 参数调整建议
        print("\n" + "=" * 60)
        print("参数调整建议")
        print("=" * 60)
        
        print("1. 如果网格层数太少（<10层）:")
        print("   - 减小ATR倍数，建议范围: 0.1 - 0.5")
        print("   - 修改配置: config/base_config.py -> grid_spacing_multiplier")
        
        print("\n2. 如果网格层数太多（>30层）:")
        print("   - 增大ATR倍数，建议范围: 0.5 - 1.0")
        print("   - 修改配置: config/base_config.py -> grid_spacing_multiplier")
        
        print("\n3. 推荐ATR倍数范围:")
        print("   - 保守策略: 0.5 - 1.0 (较少网格层数)")
        print("   - 平衡策略: 0.2 - 0.5 (适中网格层数)")  
        print("   - 激进策略: 0.1 - 0.2 (较多网格层数)")
        
        print(f"\n4. 当前设置评估:")
        if traditional_levels < 10:
            print(f"   - 网格层数偏少({traditional_levels}层)，建议减小ATR倍数")
        elif traditional_levels > 30:
            print(f"   - 网格层数偏多({traditional_levels}层)，建议增大ATR倍数")
        else:
            print(f"   - 网格层数适中({traditional_levels}层)，当前设置合理")
        
        # 当前策略使用的方法
        print(f"\n当前策略使用: 传统ATR方法")
        print(f"配置的ATR倍数: {atr_multiplier}")
        print(f"计算的网格间距: {traditional_spacing:.8f}")
        print(f"最大挂单数: {config.trading.max_open_orders}")
        print(f"实际激活的网格: {config.trading.max_open_orders} 个（动态调整）")
        
    except Exception as e:
        print(f"❌ 计算过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await connector.close()
        print("\n✓ 连接已关闭")


if __name__ == "__main__":
    asyncio.run(calculate_grid_spacing())
