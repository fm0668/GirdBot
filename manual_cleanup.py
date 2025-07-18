"""
手动清理脚本
用于清理账户中的所有挂单和持仓
"""

import asyncio
import os
from dotenv import load_dotenv
import ccxt.async_support as ccxt

from utils.logger import get_logger


class ManualCleaner:
    """手动清理器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.exchange_a = None
        self.exchange_b = None
    
    async def execute_cleanup(self, confirm_cleanup=False):
        """执行清理操作"""
        print("🧹 手动清理脚本")
        print("="*60)
        
        try:
            # 1. 初始化交易所连接
            await self._initialize_exchanges()
            
            # 2. 检查当前状态
            orders_a, orders_b, positions_a, positions_b = await self._check_current_status()
            
            total_orders = len(orders_a) + len(orders_b)
            total_positions = len(positions_a) + len(positions_b)
            
            if total_orders == 0 and total_positions == 0:
                print("\n✅ 账户已经是干净的，无需清理")
                return
            
            # 3. 显示清理计划
            print(f"\n📋 清理计划:")
            print(f"   - 将取消 {len(orders_a)} 个账户A挂单")
            print(f"   - 将取消 {len(orders_b)} 个账户B挂单")
            print(f"   - 将平仓 {len(positions_a)} 个账户A持仓")
            print(f"   - 将平仓 {len(positions_b)} 个账户B持仓")
            
            # 4. 确认执行
            if not confirm_cleanup:
                confirm = input("\n⚠️ 确认执行清理操作？这将取消所有挂单并平仓所有持仓！(输入 'YES' 确认): ")
                if confirm != 'YES':
                    print("❌ 清理操作已取消")
                    return
            
            # 5. 执行清理
            print("\n🚀 开始执行清理...")
            
            # 取消挂单
            await self._cancel_orders(self.exchange_a, orders_a, "账户A")
            await self._cancel_orders(self.exchange_b, orders_b, "账户B")
            
            # 平仓
            await self._close_positions(self.exchange_a, positions_a, "账户A")
            await self._close_positions(self.exchange_b, positions_b, "账户B")
            
            # 6. 验证清理结果
            await self._verify_cleanup()
            
            print("\n✅ 手动清理完成")
            
        except Exception as e:
            print(f"\n❌ 清理失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self._cleanup()
    
    async def _initialize_exchanges(self):
        """初始化交易所连接"""
        load_dotenv()
        
        print("📋 初始化交易所连接...")
        
        self.exchange_a = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY_A'),
            'secret': os.getenv('BINANCE_SECRET_KEY_A'),
            'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        self.exchange_b = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY_B'),
            'secret': os.getenv('BINANCE_SECRET_KEY_B'),
            'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        await self.exchange_a.load_markets()
        await self.exchange_b.load_markets()
        
        print("✅ 交易所连接初始化完成")
    
    async def _check_current_status(self):
        """检查当前状态"""
        print("\n📋 检查当前账户状态...")
        
        trading_pair = os.getenv('TRADING_PAIR')
        
        # 获取挂单
        orders_a = await self.exchange_a.fetch_open_orders(trading_pair)
        orders_b = await self.exchange_b.fetch_open_orders(trading_pair)
        
        # 获取持仓
        positions_a = await self.exchange_a.fetch_positions()
        positions_b = await self.exchange_b.fetch_positions()
        
        # 过滤出有持仓的
        active_positions_a = [pos for pos in positions_a if pos['size'] != 0]
        active_positions_b = [pos for pos in positions_b if pos['size'] != 0]
        
        print(f"✅ 账户A: {len(orders_a)} 个挂单, {len(active_positions_a)} 个持仓")
        print(f"✅ 账户B: {len(orders_b)} 个挂单, {len(active_positions_b)} 个持仓")
        
        # 显示详情
        if orders_a:
            print("   账户A挂单:")
            for order in orders_a:
                print(f"   - {order['id']}: {order['side']} {order['amount']} @ {order['price']}")
        
        if orders_b:
            print("   账户B挂单:")
            for order in orders_b:
                print(f"   - {order['id']}: {order['side']} {order['amount']} @ {order['price']}")
        
        if active_positions_a:
            print("   账户A持仓:")
            for pos in active_positions_a:
                print(f"   - {pos['symbol']}: {pos['side']} {pos['size']}")
        
        if active_positions_b:
            print("   账户B持仓:")
            for pos in active_positions_b:
                print(f"   - {pos['symbol']}: {pos['side']} {pos['size']}")
        
        return orders_a, orders_b, active_positions_a, active_positions_b
    
    async def _cancel_orders(self, exchange, orders, account_name):
        """取消订单"""
        if not orders:
            print(f"✅ {account_name}: 无挂单需要取消")
            return
        
        print(f"🔄 {account_name}: 开始取消 {len(orders)} 个挂单...")
        
        success_count = 0
        for order in orders:
            try:
                await exchange.cancel_order(order['id'], order['symbol'])
                print(f"   ✅ 已取消订单 {order['id']}")
                success_count += 1
                await asyncio.sleep(0.1)  # 避免频率限制
            except Exception as e:
                print(f"   ❌ 取消订单 {order['id']} 失败: {e}")
        
        print(f"✅ {account_name}: 撤单完成 ({success_count}/{len(orders)})")
    
    async def _close_positions(self, exchange, positions, account_name):
        """平仓"""
        if not positions:
            print(f"✅ {account_name}: 无持仓需要平仓")
            return
        
        print(f"🔄 {account_name}: 开始平仓 {len(positions)} 个持仓...")
        
        success_count = 0
        for position in positions:
            try:
                symbol = position['symbol']
                size = abs(position['size'])
                side = 'sell' if position['side'] == 'long' else 'buy'
                
                # 市价平仓
                order = await exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=size,
                    params={'reduceOnly': True}
                )
                
                print(f"   ✅ 已平仓 {symbol} {side} {size}, 订单ID: {order['id']}")
                success_count += 1
                await asyncio.sleep(0.1)  # 避免频率限制
                
            except Exception as e:
                print(f"   ❌ 平仓 {position['symbol']} 失败: {e}")
        
        print(f"✅ {account_name}: 平仓完成 ({success_count}/{len(positions)})")
    
    async def _verify_cleanup(self):
        """验证清理结果"""
        print("\n🔍 验证清理结果...")
        
        await asyncio.sleep(2)  # 等待订单处理完成
        
        trading_pair = os.getenv('TRADING_PAIR')
        
        # 重新检查状态
        orders_a = await self.exchange_a.fetch_open_orders(trading_pair)
        orders_b = await self.exchange_b.fetch_open_orders(trading_pair)
        
        positions_a = await self.exchange_a.fetch_positions()
        positions_b = await self.exchange_b.fetch_positions()
        
        active_positions_a = [pos for pos in positions_a if pos['size'] != 0]
        active_positions_b = [pos for pos in positions_b if pos['size'] != 0]
        
        total_orders = len(orders_a) + len(orders_b)
        total_positions = len(active_positions_a) + len(active_positions_b)
        
        print(f"验证结果:")
        print(f"   - 剩余挂单: {total_orders} 个")
        print(f"   - 剩余持仓: {total_positions} 个")
        
        if total_orders == 0 and total_positions == 0:
            print("✅ 清理验证通过: 账户已完全清理")
        else:
            print("⚠️ 清理不完整，可能需要手动处理剩余订单/持仓")
    
    async def _cleanup(self):
        """清理资源"""
        try:
            if self.exchange_a:
                await self.exchange_a.close()
            if self.exchange_b:
                await self.exchange_b.close()
        except Exception as e:
            print(f"❌ 清理资源失败: {e}")


async def main():
    """主函数"""
    import sys
    
    # 检查是否有自动确认参数
    auto_confirm = '--confirm' in sys.argv
    
    cleaner = ManualCleaner()
    await cleaner.execute_cleanup(confirm_cleanup=auto_confirm)


if __name__ == "__main__":
    asyncio.run(main())
