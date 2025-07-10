#!/usr/bin/env python3
"""
策略清理脚本 - 撤销所有挂单并平仓所有持仓
"""

import ccxt
from dotenv import load_dotenv
import os
import time

def main():
    load_dotenv()
    
    # 初始化交易所
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'defaultType': 'future'},
        'sandbox': False
    })
    
    symbol = 'DOGE/USDC:USDC'
    
    print("=== 策略清理开始 ===")
    
    try:
        # 1. 撤销所有未成交订单
        print("\n1. 撤销所有未成交订单...")
        open_orders = exchange.fetch_open_orders(symbol)
        
        if open_orders:
            for order in open_orders:
                try:
                    exchange.cancel_order(order['id'], symbol)
                    print(f"✅ 已撤销订单: {order['id']} ({order['side']} {order['amount']} @ {order['price']})")
                    time.sleep(0.1)  # 避免API限制
                except Exception as e:
                    print(f"❌ 撤销订单失败 {order['id']}: {e}")
        else:
            print("✅ 没有未成交订单需要撤销")
        
        # 2. 平仓所有持仓
        print("\n2. 平仓所有持仓...")
        positions = exchange.fetch_positions([symbol])
        
        for pos in positions:
            if float(pos['contracts']) != 0:
                try:
                    side = pos['side']
                    contracts = abs(float(pos['contracts']))
                    
                    # 确定平仓方向
                    if side == 'long':
                        close_side = 'sell'
                        position_side = 'LONG'
                    else:
                        close_side = 'buy' 
                        position_side = 'SHORT'
                    
                    # 执行市价平仓
                    order = exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side=close_side,
                        amount=contracts,
                        params={
                            'positionSide': position_side
                        }
                    )
                    
                    print(f"✅ 已平仓: {side.upper()} {contracts} 张 (订单ID: {order['id']})")
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"❌ 平仓失败 {side} {contracts}: {e}")
        
        # 3. 验证清理结果
        print("\n3. 验证清理结果...")
        time.sleep(2)  # 等待订单处理
        
        # 检查剩余订单
        remaining_orders = exchange.fetch_open_orders(symbol)
        if remaining_orders:
            print(f"⚠️  还有 {len(remaining_orders)} 个未成交订单")
            for order in remaining_orders:
                print(f"   订单: {order['id']} {order['side']} {order['amount']} @ {order['price']}")
        else:
            print("✅ 所有订单已清理")
        
        # 检查剩余持仓
        final_positions = exchange.fetch_positions([symbol])
        has_position = False
        for pos in final_positions:
            if float(pos['contracts']) != 0:
                print(f"⚠️  还有持仓: {pos['side'].upper()} {pos['contracts']} 张")
                has_position = True
        
        if not has_position:
            print("✅ 所有持仓已清理")
        
        # 显示最终账户状态
        print("\n=== 最终账户状态 ===")
        account_info = exchange.fetch_balance()
        usdc_balance = account_info.get('USDC', {})
        print(f"可用余额: {usdc_balance.get('free', 0)} USDC")
        print(f"占用余额: {usdc_balance.get('used', 0)} USDC") 
        print(f"总余额: {usdc_balance.get('total', 0)} USDC")
        
        print("\n=== 清理完成 ===")
        
    except Exception as e:
        print(f"❌ 清理过程中出现错误: {e}")

if __name__ == "__main__":
    main()
