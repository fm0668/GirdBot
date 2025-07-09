#!/usr/bin/env python3
"""
检查DOGEUSDC的交易规则和精度
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.production import ProductionConfig
from src.exchange.binance_connector_v2 import BinanceConnectorV2
from loguru import logger

async def check_symbol_info():
    """检查交易对信息"""
    try:
        # 创建连接器
        prod_config = ProductionConfig()
        connector = BinanceConnectorV2(
            api_key=prod_config.api_long.api_key,
            api_secret=prod_config.api_long.api_secret,
            testnet=prod_config.api_long.testnet
        )
        
        # 建立连接
        await connector.connect()
        
        # 获取交易对信息
        symbol = "DOGEUSDC"
        logger.info(f"获取 {symbol} 交易规则...")
        
        exchange_info = await connector.get_exchange_info()
        
        # 查找DOGEUSDC的信息
        symbol_info = None
        for s in exchange_info.get('symbols', []):
            if s['symbol'] == symbol:
                symbol_info = s
                break
        
        if symbol_info:
            logger.info(f"✅ 找到 {symbol} 信息:")
            logger.info(f"   交易状态: {symbol_info.get('status', 'UNKNOWN')}")
            logger.info(f"   基础资产: {symbol_info.get('baseAsset', 'UNKNOWN')}")
            logger.info(f"   计价资产: {symbol_info.get('quoteAsset', 'UNKNOWN')}")
            
            # 过滤器信息
            logger.info("   交易规则:")
            for filter_info in symbol_info.get('filters', []):
                filter_type = filter_info.get('filterType')
                if filter_type == 'PRICE_FILTER':
                    logger.info(f"     价格过滤器:")
                    logger.info(f"       最小价格: {filter_info.get('minPrice', 'N/A')}")
                    logger.info(f"       最大价格: {filter_info.get('maxPrice', 'N/A')}")
                    logger.info(f"       价格步长: {filter_info.get('tickSize', 'N/A')}")
                elif filter_type == 'LOT_SIZE':
                    logger.info(f"     数量过滤器:")
                    logger.info(f"       最小数量: {filter_info.get('minQty', 'N/A')}")
                    logger.info(f"       最大数量: {filter_info.get('maxQty', 'N/A')}")
                    logger.info(f"       数量步长: {filter_info.get('stepSize', 'N/A')}")
                elif filter_info == 'MIN_NOTIONAL':
                    logger.info(f"     最小名义价值: {filter_info.get('minNotional', 'N/A')}")
            
            # 精度信息
            logger.info(f"   基础资产精度: {symbol_info.get('baseAssetPrecision', 'UNKNOWN')}")
            logger.info(f"   计价资产精度: {symbol_info.get('quoteAssetPrecision', 'UNKNOWN')}")
            
        else:
            logger.error(f"❌ 未找到 {symbol} 交易对信息")
        
        # 关闭连接器
        await connector.close()
        
    except Exception as e:
        logger.error(f"检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_symbol_info())
