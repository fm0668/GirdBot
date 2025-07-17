"""
交易所数据提供器
目的：动态获取交易所数据，包括手续费、保证金率、精度等信息
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import ccxt.async_support as ccxt

from utils.logger import get_logger
from utils.exceptions import ExchangeAPIError
from config.binance_official_data import BinanceOfficialData


@dataclass
class TradingSymbolInfo:
    """交易对信息"""
    symbol: str
    base_asset: str
    quote_asset: str
    
    # 精度信息
    price_precision: int
    amount_precision: int
    cost_precision: int
    
    # 限制信息
    min_amount: Decimal
    max_amount: Decimal
    min_cost: Decimal
    max_cost: Decimal
    min_price: Decimal
    max_price: Decimal
    
    # 手续费信息
    maker_fee: Decimal
    taker_fee: Decimal
    
    # 保证金信息
    maintenance_margin_rate: Decimal
    initial_margin_rate: Decimal
    
    # 更新时间
    last_updated: datetime


class ExchangeDataProvider:
    """交易所数据提供器"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self.logger = get_logger(self.__class__.__name__)
        
        # 缓存机制
        self._symbol_info_cache: Dict[str, TradingSymbolInfo] = {}
        self._cache_ttl = timedelta(hours=1)  # 缓存1小时
        
        # 数据获取锁
        self._data_lock = asyncio.Lock()
    
    async def get_symbol_info(self, symbol: str, force_refresh: bool = False) -> TradingSymbolInfo:
        """
        获取交易对完整信息
        
        Args:
            symbol: 交易对符号
            force_refresh: 是否强制刷新缓存
        
        Returns:
            交易对信息
        """
        try:
            async with self._data_lock:
                # 检查缓存
                if not force_refresh and symbol in self._symbol_info_cache:
                    cached_info = self._symbol_info_cache[symbol]
                    if datetime.utcnow() - cached_info.last_updated < self._cache_ttl:
                        self.logger.debug(f"使用缓存的交易对信息: {symbol}")
                        return cached_info
                
                self.logger.info(f"获取交易对信息: {symbol}")
                
                # 确保市场数据已加载
                if not self.exchange.markets:
                    await self.exchange.load_markets()
                
                # 获取市场信息
                market = self.exchange.markets.get(symbol)
                if not market:
                    raise ExchangeAPIError(f"交易对 {symbol} 不存在")
                
                # 获取手续费信息
                trading_fees = await self._get_trading_fees(symbol)
                
                # 获取保证金信息
                margin_info = await self._get_margin_info(symbol)
                
                # 构建交易对信息
                symbol_info = TradingSymbolInfo(
                    symbol=symbol,
                    base_asset=market['base'],
                    quote_asset=market['quote'],
                    
                    # 精度信息
                    price_precision=market['precision']['price'],
                    amount_precision=market['precision']['amount'],
                    cost_precision=market['precision'].get('cost', 8),
                    
                    # 限制信息
                    min_amount=Decimal(str(market['limits']['amount']['min'] or 0)),
                    max_amount=Decimal(str(market['limits']['amount']['max'] or 999999999)),
                    min_cost=Decimal(str(market['limits']['cost']['min'] or 0)),
                    max_cost=Decimal(str(market['limits']['cost']['max'] or 999999999)),
                    min_price=Decimal(str(market['limits']['price']['min'] or 0)),
                    max_price=Decimal(str(market['limits']['price']['max'] or 999999999)),
                    
                    # 手续费信息
                    maker_fee=trading_fees['maker'],
                    taker_fee=trading_fees['taker'],
                    
                    # 保证金信息
                    maintenance_margin_rate=margin_info['maintenance_margin_rate'],
                    initial_margin_rate=margin_info['initial_margin_rate'],
                    
                    last_updated=datetime.utcnow()
                )
                
                # 更新缓存
                self._symbol_info_cache[symbol] = symbol_info
                
                self.logger.info(f"交易对信息获取完成: {symbol}", extra={
                    'maker_fee': str(symbol_info.maker_fee),
                    'taker_fee': str(symbol_info.taker_fee),
                    'maintenance_margin_rate': str(symbol_info.maintenance_margin_rate),
                    'amount_precision': symbol_info.amount_precision,
                    'min_cost': str(symbol_info.min_cost)
                })
                
                return symbol_info
                
        except Exception as e:
            self.logger.error(f"获取交易对信息失败: {symbol}, 错误: {e}")
            raise ExchangeAPIError(f"获取交易对信息失败: {str(e)}")
    
    async def _get_trading_fees(self, symbol: str) -> Dict[str, Decimal]:
        """
        获取交易手续费

        Args:
            symbol: 交易对符号

        Returns:
            手续费信息字典
        """
        try:
            # 方法1: 直接调用币安API获取用户特定手续费
            try:
                if hasattr(self.exchange, 'fapiPrivateGetCommissionRate'):
                    # 转换符号格式 (DOGE/USDC:USDC -> DOGEUSDC)
                    binance_symbol = symbol.replace('/', '').replace(':USDC', '').replace(':USDT', '')
                    self.logger.info(f"尝试获取用户手续费，符号: {binance_symbol}")

                    response = await self.exchange.fapiPrivateGetCommissionRate({'symbol': binance_symbol})
                    self.logger.info(f"成功获取用户手续费: {response}")

                    maker_rate = Decimal(str(response.get('makerCommissionRate', '0.0002')))
                    taker_rate = Decimal(str(response.get('takerCommissionRate', '0.0004')))

                    self.logger.info(f"用户手续费: Maker={maker_rate*100:.4f}%, Taker={taker_rate*100:.4f}%")

                    return {
                        'maker': maker_rate,
                        'taker': taker_rate
                    }
                else:
                    self.logger.warning("交易所不支持fapiPrivateGetCommissionRate方法")
            except Exception as e:
                self.logger.warning(f"获取用户特定手续费失败: {e}")

            # 方法2: 尝试使用ccxt的fetch_trading_fees（可能不稳定）
            try:
                fees = await self.exchange.fetch_trading_fees([symbol])
                if symbol in fees:
                    fee_info = fees[symbol]
                    return {
                        'maker': Decimal(str(fee_info.get('maker', 0.0002))),
                        'taker': Decimal(str(fee_info.get('taker', 0.0004)))
                    }
            except Exception as e:
                self.logger.debug(f"ccxt fetch_trading_fees失败: {e}")

            # 方法3: 从市场信息中获取（通常是默认费率）
            if self.exchange.markets and symbol in self.exchange.markets:
                market = self.exchange.markets[symbol]
                maker_fee = Decimal(str(market.get('maker', 0.0002)))
                taker_fee = Decimal(str(market.get('taker', 0.0004)))

                self.logger.info(f"使用市场默认手续费: Maker={maker_fee*100:.4f}%, Taker={taker_fee*100:.4f}%")
                return {
                    'maker': maker_fee,
                    'taker': taker_fee
                }

            # 方法4: 使用币安官方默认费率
            self.logger.warning(f"无法获取 {symbol} 的手续费，使用官方默认费率")
            if 'USDC' in symbol:
                return {
                    'maker': Decimal("0.0000"),  # 0.00% USDC挂单手续费（普通用户）
                    'taker': Decimal("0.0004")   # 0.04% USDC吃单手续费（实际API返回值）
                }
            else:
                return {
                    'maker': Decimal("0.0002"),  # 0.02% USDT默认挂单手续费
                    'taker': Decimal("0.0004")   # 0.04% USDT默认吃单手续费
                }

        except Exception as e:
            self.logger.error(f"获取交易手续费失败: {e}")
            # 根据交易对使用对应的默认费率
            if 'USDC' in symbol:
                return {
                    'maker': Decimal("0.0000"),  # USDC普通用户
                    'taker': Decimal("0.0004")   # 使用实际API返回值
                }
            else:
                return {
                    'maker': Decimal("0.0002"),  # USDT默认
                    'taker': Decimal("0.0004")
                }
    
    async def _get_margin_info(self, symbol: str) -> Dict[str, Decimal]:
        """
        获取保证金信息

        Args:
            symbol: 交易对符号

        Returns:
            保证金信息字典
        """
        try:
            # 方法1: 使用ccxt的fetch_leverage_tiers获取杠杆分层信息
            try:
                if hasattr(self.exchange, 'fetch_leverage_tiers'):
                    tiers = await self.exchange.fetch_leverage_tiers([symbol])
                    self.logger.info(f"成功获取杠杆分层数据")

                    if symbol in tiers and tiers[symbol]:
                        # 取第一层的保证金率
                        first_tier = tiers[symbol][0]

                        # ccxt已经处理好了数据格式，直接使用
                        mmr = Decimal(str(first_tier.get('maintenanceMarginRate', 0.05)))
                        max_leverage = int(first_tier.get('maxLeverage', 20))

                        # 计算初始保证金率 = 1 / 最大杠杆
                        imr = Decimal('1') / Decimal(str(max_leverage))

                        self.logger.info(f"杠杆分层数据: MMR={mmr*100:.3f}%, 最大杠杆={max_leverage}x, IMR={imr*100:.3f}%")

                        return {
                            'maintenance_margin_rate': mmr,
                            'initial_margin_rate': imr
                        }
            except Exception as e:
                self.logger.debug(f"获取杠杆分层信息失败: {e}")

            # 方法2: 直接调用币安API获取杠杆分层
            try:
                if hasattr(self.exchange, 'fapiPrivateGetLeverageBracket'):
                    # 转换符号格式
                    binance_symbol = symbol.replace('/', '').replace(':USDC', '').replace(':USDT', '')

                    response = await self.exchange.fapiPrivateGetLeverageBracket({'symbol': binance_symbol})
                    self.logger.info(f"直接API获取杠杆分层成功")

                    if response and len(response) > 0:
                        brackets = response[0].get('brackets', [])
                        if brackets:
                            # 取第一层数据
                            first_bracket = brackets[0]

                            mmr = Decimal(str(first_bracket.get('maintMarginRatio', '0.05')))
                            max_leverage = int(first_bracket.get('initialLeverage', '20'))
                            imr = Decimal('1') / Decimal(str(max_leverage))

                            self.logger.info(f"API杠杆分层数据: MMR={mmr*100:.3f}%, 最大杠杆={max_leverage}x, IMR={imr*100:.3f}%")

                            return {
                                'maintenance_margin_rate': mmr,
                                'initial_margin_rate': imr
                            }
            except Exception as e:
                self.logger.debug(f"直接API获取杠杆分层失败: {e}")

            # 方法2: 尝试获取市场信息中的保证金率
            try:
                if self.exchange.markets and symbol in self.exchange.markets:
                    market = self.exchange.markets[symbol]
                    info = market.get('info', {})

                    raw_mmr = info.get('maintMarginPercent', 0.05)
                    raw_imr = info.get('requiredMarginPercent', 0.1)

                    self.logger.debug(f"市场信息中的保证金率: MMR={raw_mmr}, IMR={raw_imr}")

                    # 币安API返回的是百分比数值，需要转换
                    # 例如：2.5000 表示 2.5%，需要转换为 0.025
                    if isinstance(raw_mmr, (int, float)):
                        mmr = Decimal(str(raw_mmr / 100))  # 转换为小数
                    else:
                        mmr = Decimal(str(raw_mmr))

                    if isinstance(raw_imr, (int, float)):
                        imr = Decimal(str(raw_imr / 100))  # 转换为小数
                    else:
                        imr = Decimal(str(raw_imr))

                    # 但是市场信息中的数据可能不准确，使用官方数据
                    self.logger.warning("市场信息中的保证金率可能不准确，使用官方分层数据")

                    # 直接跳到默认值处理
            except Exception as e:
                self.logger.debug(f"从市场信息获取保证金率失败: {e}")

            # 使用币安官方数据作为默认值
            self.logger.warning(f"无法获取 {symbol} 的保证金率，使用官方默认数据")
            if 'DOGE' in symbol and 'USDC' in symbol:
                # 使用测试验证的DOGEUSDC第1层数据
                return {
                    'maintenance_margin_rate': Decimal("0.005"),   # 0.50% (API验证正确)
                    'initial_margin_rate': Decimal("0.0133")       # 1.33% (1/75)
                }
            else:
                return {
                    'maintenance_margin_rate': Decimal("0.05"),    # 5% 通用默认值
                    'initial_margin_rate': Decimal("0.1")         # 10% 通用默认值
                }

        except Exception as e:
            self.logger.error(f"获取保证金信息失败: {e}")
            # 根据交易对使用对应的默认值
            if 'DOGE' in symbol and 'USDC' in symbol:
                return {
                    'maintenance_margin_rate': Decimal("0.005"),   # DOGEUSDC第1层 (API验证)
                    'initial_margin_rate': Decimal("0.0133")       # 1/75
                }
            else:
                return {
                    'maintenance_margin_rate': Decimal("0.05"),    # 通用默认值
                    'initial_margin_rate': Decimal("0.1")
                }

    def _validate_margin_rates(self, mmr: Decimal, imr: Decimal) -> Tuple[Decimal, Decimal]:
        """
        验证保证金率数据的合理性

        Args:
            mmr: 维持保证金率
            imr: 初始保证金率

        Returns:
            验证后的保证金率
        """
        # MMR应该在0.1%到10%之间
        if mmr < Decimal("0.001") or mmr > Decimal("0.1"):
            self.logger.warning(f"异常的维持保证金率: {mmr*100:.3f}%, 使用DOGEUSDC官方值0.50%")
            mmr = Decimal("0.005")  # 使用币安官方DOGEUSDC第1层数据

        # IMR应该大于等于MMR，且不超过20%
        if imr < mmr:
            imr = mmr * Decimal("2")  # 设为MMR的2倍
            self.logger.warning(f"初始保证金率小于维持保证金率，调整为: {imr*100:.3f}%")
        elif imr > Decimal("0.2"):
            imr = Decimal("0.2")  # 最大20%
            self.logger.warning(f"初始保证金率过高，调整为: 20%")

        return mmr, imr
    
    async def get_current_price(self, symbol: str) -> Decimal:
        """
        获取当前价格
        
        Args:
            symbol: 交易对符号
        
        Returns:
            当前价格
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return Decimal(str(ticker['last']))
        except Exception as e:
            self.logger.error(f"获取当前价格失败: {symbol}, 错误: {e}")
            raise ExchangeAPIError(f"获取当前价格失败: {str(e)}")
    
    def format_amount(self, symbol: str, amount: Decimal) -> Decimal:
        """
        格式化订单数量到正确精度
        
        Args:
            symbol: 交易对符号
            amount: 原始数量
        
        Returns:
            格式化后的数量
        """
        try:
            if symbol in self._symbol_info_cache:
                symbol_info = self._symbol_info_cache[symbol]
                precision = symbol_info.amount_precision
                
                # 使用向下取整，避免超出限制
                import math
                factor = 10 ** precision
                return Decimal(str(math.floor(float(amount) * factor) / factor))
            
            # 默认保留6位小数
            return amount.quantize(Decimal('0.000001'))
            
        except Exception:
            return amount.quantize(Decimal('0.000001'))
    
    def format_price(self, symbol: str, price: Decimal) -> Decimal:
        """
        格式化价格到正确精度
        
        Args:
            symbol: 交易对符号
            price: 原始价格
        
        Returns:
            格式化后的价格
        """
        try:
            if symbol in self._symbol_info_cache:
                symbol_info = self._symbol_info_cache[symbol]
                precision = symbol_info.price_precision
                
                factor = 10 ** precision
                return Decimal(str(round(float(price) * factor) / factor))
            
            # 默认保留8位小数
            return price.quantize(Decimal('0.00000001'))
            
        except Exception:
            return price.quantize(Decimal('0.00000001'))
    
    async def clear_cache(self):
        """清除缓存"""
        async with self._data_lock:
            self._symbol_info_cache.clear()
            self.logger.info("交易所数据缓存已清除")
