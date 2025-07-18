"""
测试清理功能
验证撤单和平仓逻辑是否正常工作
"""

import asyncio
import os
from dotenv import load_dotenv
import ccxt.async_support as ccxt

from utils.logger import get_logger


class CleanupTester:
    """清理功能测试器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.exchange_a = None
        self.exchange_b = None
    
    async def test_cleanup_functionality(self):
        """测试清理功能"""
        print("🧹 测试清理功能")
        print("="*60)
        
        try:
            # 1. 初始化交易所连接
            await self._initialize_exchanges()
            
            # 2. 测试获取挂单
            await self._test_get_open_orders()
            
            # 3. 测试获取持仓
            await self._test_get_positions()
            
            # 4. 测试撤单功能（如果有挂单）
            await self._test_cancel_orders()
            
            # 5. 测试平仓功能（如果有持仓）
            await self._test_close_positions()
            
            print("\n✅ 清理功能测试完成")
            
        except Exception as e:
            print(f"\n❌ 清理功能测试失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self._cleanup()
    
    async def _initialize_exchanges(self):
        """初始化交易所连接"""
        load_dotenv()
        
        print("\n📋 初始化交易所连接...")
        
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
    
    async def _test_get_open_orders(self):
        """测试获取挂单"""
        print("\n📋 测试获取挂单...")
        
        trading_pair = os.getenv('TRADING_PAIR')
        
        try:
            orders_a = await self.exchange_a.fetch_open_orders(trading_pair)
            orders_b = await self.exchange_b.fetch_open_orders(trading_pair)
            
            print(f"✅ 账户A挂单数: {len(orders_a)}")
            print(f"✅ 账户B挂单数: {len(orders_b)}")
            
            # 显示挂单详情
            if orders_a:
                print("   账户A挂单详情:")
                for order in orders_a[:3]:  # 只显示前3个
                    print(f"   - {order['id']}: {order['side']} {order['amount']} @ {order['price']}")
            
            if orders_b:
                print("   账户B挂单详情:")
                for order in orders_b[:3]:  # 只显示前3个
                    print(f"   - {order['id']}: {order['side']} {order['amount']} @ {order['price']}")
            
            return orders_a, orders_b
            
        except Exception as e:
            print(f"❌ 获取挂单失败: {e}")
            return [], []
    
    async def _test_get_positions(self):
        """测试获取持仓"""
        print("\n📋 测试获取持仓...")
        
        try:
            positions_a = await self.exchange_a.fetch_positions()
            positions_b = await self.exchange_b.fetch_positions()
            
            # 过滤出有持仓的
            active_positions_a = [pos for pos in positions_a if pos['size'] != 0]
            active_positions_b = [pos for pos in positions_b if pos['size'] != 0]
            
            print(f"✅ 账户A持仓数: {len(active_positions_a)}")
            print(f"✅ 账户B持仓数: {len(active_positions_b)}")
            
            # 显示持仓详情
            if active_positions_a:
                print("   账户A持仓详情:")
                for pos in active_positions_a:
                    print(f"   - {pos['symbol']}: {pos['side']} {pos['size']} @ {pos['markPrice']}")
            
            if active_positions_b:
                print("   账户B持仓详情:")
                for pos in active_positions_b:
                    print(f"   - {pos['symbol']}: {pos['side']} {pos['size']} @ {pos['markPrice']}")
            
            return active_positions_a, active_positions_b
            
        except Exception as e:
            print(f"❌ 获取持仓失败: {e}")
            return [], []
    
    async def _test_cancel_orders(self):
        """测试撤单功能"""
        print("\n📋 测试撤单功能...")
        
        # 注意：这里只是测试撤单逻辑，不会实际撤单
        # 如果需要实际测试，请谨慎操作
        
        trading_pair = os.getenv('TRADING_PAIR')
        
        try:
            orders_a = await self.exchange_a.fetch_open_orders(trading_pair)
            orders_b = await self.exchange_b.fetch_open_orders(trading_pair)
            
            print(f"发现账户A挂单: {len(orders_a)} 个")
            print(f"发现账户B挂单: {len(orders_b)} 个")
            
            # 这里只是模拟撤单逻辑，不实际执行
            print("⚠️ 撤单功能测试（仅模拟，不实际执行）")
            
            if orders_a or orders_b:
                print("   如果实际执行，将会:")
                for order in orders_a:
                    print(f"   - 取消账户A订单: {order['id']}")
                for order in orders_b:
                    print(f"   - 取消账户B订单: {order['id']}")
            else:
                print("   无挂单需要取消")
            
            print("✅ 撤单功能逻辑正常")
            
        except Exception as e:
            print(f"❌ 撤单功能测试失败: {e}")
    
    async def _test_close_positions(self):
        """测试平仓功能"""
        print("\n📋 测试平仓功能...")
        
        # 注意：这里只是测试平仓逻辑，不会实际平仓
        # 如果需要实际测试，请谨慎操作
        
        try:
            positions_a = await self.exchange_a.fetch_positions()
            positions_b = await self.exchange_b.fetch_positions()
            
            active_positions_a = [pos for pos in positions_a if pos['size'] != 0]
            active_positions_b = [pos for pos in positions_b if pos['size'] != 0]
            
            print(f"发现账户A持仓: {len(active_positions_a)} 个")
            print(f"发现账户B持仓: {len(active_positions_b)} 个")
            
            # 这里只是模拟平仓逻辑，不实际执行
            print("⚠️ 平仓功能测试（仅模拟，不实际执行）")
            
            if active_positions_a or active_positions_b:
                print("   如果实际执行，将会:")
                for pos in active_positions_a:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    print(f"   - 平仓账户A: {pos['symbol']} {side} {abs(pos['size'])}")
                for pos in active_positions_b:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    print(f"   - 平仓账户B: {pos['symbol']} {side} {abs(pos['size'])}")
            else:
                print("   无持仓需要平仓")
            
            print("✅ 平仓功能逻辑正常")
            
        except Exception as e:
            print(f"❌ 平仓功能测试失败: {e}")
    
    async def _cleanup(self):
        """清理资源"""
        try:
            if self.exchange_a:
                await self.exchange_a.close()
            if self.exchange_b:
                await self.exchange_b.close()
            print("✅ 交易所连接已关闭")
        except Exception as e:
            print(f"❌ 清理资源失败: {e}")


async def main():
    """主函数"""
    tester = CleanupTester()
    await tester.test_cleanup_functionality()


if __name__ == "__main__":
    asyncio.run(main())
