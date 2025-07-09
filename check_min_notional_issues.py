#!/usr/bin/env python3
"""
检查并修复 calculate_grid_parameters 调用中的 min_notional 参数问题
"""

import os
import sys
sys.path.append('/root/GirdBot')

import asyncio
from decimal import Decimal
from src.core.grid_calculator import GridCalculator
from src.core.binance_compatibility import BinanceAPICompatibilityHandler
from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig

async def main():
    print("【检查和修复 min_notional 参数问题】")
    print("=" * 60)
    
    # 1. 检查所有调用 calculate_grid_parameters 的地方
    print("\n1️⃣ 检查所有调用 calculate_grid_parameters 的地方...")
    
    # 从 grep 结果看主要有以下几个文件调用了该方法：
    call_locations = [
        "/root/GirdBot/src/core/grid_strategy.py",
        "/root/GirdBot/test_real_mmr.py", 
        "/root/GirdBot/test_optimized_grid_parameters.py",
        "/root/GirdBot/final_verification.py"
    ]
    
    for file_path in call_locations:
        if os.path.exists(file_path):
            print(f"\n📁 检查文件: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 查找 calculate_grid_parameters 调用
            if "calculate_grid_parameters" in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if "calculate_grid_parameters" in line:
                        print(f"   第{i+1}行: {line.strip()}")
                        
                        # 检查是否有 min_notional 参数
                        context_start = max(0, i-3)
                        context_end = min(len(lines), i+10)
                        context = '\n'.join(lines[context_start:context_end])
                        
                        if "min_notional" in context:
                            print(f"   ⚠️  发现显式传递 min_notional 参数")
                            print(f"   上下文:\n{context}")
                            print()
    
    # 2. 测试动态获取 min_notional
    print("\n2️⃣ 测试动态获取 min_notional...")
    
    # 使用模拟API密钥进行测试
    connector = BinanceConnector(
        api_key="test_api_key",
        api_secret="test_api_secret",
        testnet=True
    )
    
    try:
        await connector.connect()
        
        # 初始化网格计算器
        calculator = GridCalculator()
        
        # 测试不传递 min_notional 参数（应该自动从API获取）
        print("   测试不传递 min_notional 参数...")
        params = await calculator.calculate_grid_parameters(
            upper_bound=Decimal("0.18"),
            lower_bound=Decimal("0.16"),
            atr_value=Decimal("0.005"),
            atr_multiplier=Decimal("0.26"),
            unified_margin=Decimal("100"),
            connector=connector,
            symbol="DOGEUSDC"
            # 注意：这里不传递 min_notional 参数
        )
        
        print(f"   ✅ 成功获取网格参数")
        print(f"   每格金额: {params['amount_per_grid']:.2f} USDC")
        
        # 测试传递 min_notional=None（应该自动从API获取）
        print("\n   测试传递 min_notional=None...")
        params2 = await calculator.calculate_grid_parameters(
            upper_bound=Decimal("0.18"),
            lower_bound=Decimal("0.16"),
            atr_value=Decimal("0.005"),
            atr_multiplier=Decimal("0.26"),
            unified_margin=Decimal("100"),
            connector=connector,
            symbol="DOGEUSDC",
            min_notional=None  # 明确传递 None
        )
        
        print(f"   ✅ 成功获取网格参数")
        print(f"   每格金额: {params2['amount_per_grid']:.2f} USDC")
        
        # 验证兼容性处理器获取的最小名义价值
        compatibility_handler = BinanceAPICompatibilityHandler(connector)
        symbol_info = await compatibility_handler.get_symbol_info_safe("DOGEUSDC")
        
        if symbol_info and 'filters_info' in symbol_info:
            notional_info = symbol_info['filters_info'].get('notional', {})
            api_min_notional = notional_info.get('min', 'N/A')
            print(f"\n   从 API 获取的最小名义价值: {api_min_notional} USDC")
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
    finally:
        await connector.close()
    
    # 3. 检查其他交易对的支持
    print("\n3️⃣ 检查其他交易对的 MIN_NOTIONAL 支持...")
    
    # 常见的永续合约交易对
    test_symbols = ["BTCUSDC", "ETHUSDC", "DOGEUSDC", "SOLUSDC"]
    
    try:
        # 使用模拟API密钥进行测试
        connector = BinanceConnector(
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=True
        )
        await connector.connect()
        
        compatibility_handler = BinanceAPICompatibilityHandler(connector)
        
        for symbol in test_symbols:
            try:
                symbol_info = await compatibility_handler.get_symbol_info_safe(symbol)
                if symbol_info and 'filters_info' in symbol_info:
                    notional_info = symbol_info['filters_info'].get('notional', {})
                    min_notional = notional_info.get('min', 'N/A')
                    print(f"   {symbol}: MIN_NOTIONAL = {min_notional} USDC")
                else:
                    print(f"   {symbol}: ❌ 无法获取交易对信息")
            except Exception as e:
                print(f"   {symbol}: ❌ 获取失败 - {e}")
        
        await connector.close()
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
