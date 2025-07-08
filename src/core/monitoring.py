"""
监控和日志系统
负责策略运行状态监控、性能追踪、风险警报等功能
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime
from dataclasses import asdict

from .data_structures import (
    PerformanceMetrics, RiskMetrics
)


class MonitoringSystem:
    """监控系统"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化监控系统
        
        Args:
            config: 监控配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 监控状态
        self.is_running = False
        self.start_time: Optional[float] = None
        self.last_report_time = 0
        
        # 性能数据缓存
        self.performance_history: List[Dict] = []
        self.risk_history: List[Dict] = []
        self.alert_history: List[Dict] = []
        
        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        
        # 风险阈值
        self.risk_thresholds = {
            "max_margin_ratio": config.get("max_margin_ratio", 0.8),
            "max_drawdown": config.get("max_drawdown", 0.1),
            "min_balance_ratio": config.get("min_balance_ratio", 0.9)
        }
    
    def start_monitoring(self):
        """启动监控"""
        if self.is_running:
            self.logger.warning("监控系统已在运行")
            return
        
        self.is_running = True
        self.start_time = time.time()
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("监控系统已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        self.is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        self.logger.info("监控系统已停止")
    
    async def _monitoring_loop(self):
        """监控主循环"""
        while self.is_running:
            try:
                # 检查是否需要生成报告
                current_time = time.time()
                report_interval = self.config.get("report_interval", 300)  # 5分钟
                
                if current_time - self.last_report_time >= report_interval:
                    await self._generate_status_report()
                    self.last_report_time = current_time
                
                await asyncio.sleep(30)  # 30秒检查一次
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(60)
    
    async def record_performance(self, metrics: PerformanceMetrics):
        """
        记录性能指标
        
        Args:
            metrics: 性能指标
        """
        try:
            record = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                **asdict(metrics)
            }
            
            self.performance_history.append(record)
            
            # 保持历史记录在合理范围内
            max_records = self.config.get("max_performance_records", 1000)
            if len(self.performance_history) > max_records:
                self.performance_history = self.performance_history[-max_records:]
            
            self.logger.debug(f"记录性能指标: {record}")
            
        except Exception as e:
            self.logger.error(f"记录性能指标失败: {e}")
    
    async def record_risk_metrics(self, metrics: RiskMetrics):
        """
        记录风险指标
        
        Args:
            metrics: 风险指标
        """
        try:
            record = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                **asdict(metrics)
            }
            
            self.risk_history.append(record)
            
            # 保持历史记录在合理范围内
            max_records = self.config.get("max_risk_records", 1000)
            if len(self.risk_history) > max_records:
                self.risk_history = self.risk_history[-max_records:]
            
            # 检查风险警报
            await self._check_risk_alerts(metrics)
            
            self.logger.debug(f"记录风险指标: {record}")
            
        except Exception as e:
            self.logger.error(f"记录风险指标失败: {e}")
    
    async def _check_risk_alerts(self, metrics: RiskMetrics):
        """
        检查风险警报
        
        Args:
            metrics: 风险指标
        """
        alerts = []
        
        # 检查保证金比率
        if metrics.margin_ratio > Decimal(str(self.risk_thresholds["max_margin_ratio"])):
            alerts.append({
                "type": "HIGH_MARGIN_RATIO",
                "message": f"保证金比率过高: {metrics.margin_ratio:.2%}",
                "severity": "WARNING",
                "value": float(metrics.margin_ratio)
            })
        
        # 检查最大回撤
        if metrics.max_drawdown > Decimal(str(self.risk_thresholds["max_drawdown"])):
            alerts.append({
                "type": "HIGH_DRAWDOWN",
                "message": f"回撤过大: {metrics.max_drawdown:.2%}",
                "severity": "CRITICAL",
                "value": float(metrics.max_drawdown)
            })
        
        # 记录警报
        for alert in alerts:
            await self._record_alert(alert)
    
    async def _record_alert(self, alert: Dict):
        """
        记录警报
        
        Args:
            alert: 警报信息
        """
        alert_record = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            **alert
        }
        
        self.alert_history.append(alert_record)
        
        # 保持警报历史在合理范围内
        max_alerts = self.config.get("max_alert_records", 500)
        if len(self.alert_history) > max_alerts:
            self.alert_history = self.alert_history[-max_alerts:]
        
        # 根据严重程度选择日志级别
        if alert["severity"] == "CRITICAL":
            self.logger.critical(f"风险警报: {alert['message']}")
        elif alert["severity"] == "WARNING":
            self.logger.warning(f"风险警报: {alert['message']}")
        else:
            self.logger.info(f"风险警报: {alert['message']}")
    
    async def _generate_status_report(self):
        """生成状态报告"""
        try:
            report = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                "uptime": time.time() - self.start_time if self.start_time else 0,
                "performance_records": len(self.performance_history),
                "risk_records": len(self.risk_history),
                "alert_count": len(self.alert_history)
            }
            
            # 最近性能指标
            if self.performance_history:
                latest_perf = self.performance_history[-1]
                report["latest_performance"] = {
                    "total_trades": latest_perf.get("total_trades", 0),
                    "total_profit": latest_perf.get("total_profit", 0),
                    "win_rate": latest_perf.get("win_rate", 0)
                }
            
            # 最近风险指标
            if self.risk_history:
                latest_risk = self.risk_history[-1]
                report["latest_risk"] = {
                    "margin_ratio": latest_risk.get("margin_ratio", 0),
                    "unrealized_pnl": latest_risk.get("unrealized_pnl", 0),
                    "net_exposure": latest_risk.get("net_exposure", 0)
                }
            
            # 最近警报
            recent_alerts = [alert for alert in self.alert_history 
                           if time.time() - alert["timestamp"] < 3600]  # 最近1小时
            report["recent_alerts"] = len(recent_alerts)
            
            self.logger.info(f"状态报告: {report}")
            
        except Exception as e:
            self.logger.error(f"生成状态报告失败: {e}")
    
    def get_performance_summary(self, hours: int = 24) -> Dict:
        """
        获取性能摘要
        
        Args:
            hours: 时间范围（小时）
            
        Returns:
            Dict: 性能摘要
        """
        try:
            cutoff_time = time.time() - (hours * 3600)
            recent_records = [r for r in self.performance_history 
                            if r["timestamp"] > cutoff_time]
            
            if not recent_records:
                return {"error": "没有足够的数据"}
            
            # 计算统计信息
            total_trades = [r.get("total_trades", 0) for r in recent_records]
            total_profits = [r.get("total_profit", 0) for r in recent_records]
            
            summary = {
                "time_range_hours": hours,
                "record_count": len(recent_records),
                "trades_change": max(total_trades) - min(total_trades) if total_trades else 0,
                "profit_change": max(total_profits) - min(total_profits) if total_profits else 0,
                "latest_metrics": recent_records[-1] if recent_records else {}
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取性能摘要失败: {e}")
            return {"error": str(e)}
    
    def get_risk_summary(self, hours: int = 24) -> Dict:
        """
        获取风险摘要
        
        Args:
            hours: 时间范围（小时）
            
        Returns:
            Dict: 风险摘要
        """
        try:
            cutoff_time = time.time() - (hours * 3600)
            recent_records = [r for r in self.risk_history 
                            if r["timestamp"] > cutoff_time]
            
            if not recent_records:
                return {"error": "没有足够的数据"}
            
            # 计算风险统计
            margin_ratios = [r.get("margin_ratio", 0) for r in recent_records]
            unrealized_pnls = [r.get("unrealized_pnl", 0) for r in recent_records]
            
            summary = {
                "time_range_hours": hours,
                "record_count": len(recent_records),
                "max_margin_ratio": max(margin_ratios) if margin_ratios else 0,
                "min_margin_ratio": min(margin_ratios) if margin_ratios else 0,
                "max_unrealized_pnl": max(unrealized_pnls) if unrealized_pnls else 0,
                "min_unrealized_pnl": min(unrealized_pnls) if unrealized_pnls else 0,
                "latest_metrics": recent_records[-1] if recent_records else {}
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取风险摘要失败: {e}")
            return {"error": str(e)}
    
    def get_alert_summary(self, hours: int = 24) -> Dict:
        """
        获取警报摘要
        
        Args:
            hours: 时间范围（小时）
            
        Returns:
            Dict: 警报摘要
        """
        try:
            cutoff_time = time.time() - (hours * 3600)
            recent_alerts = [a for a in self.alert_history 
                           if a["timestamp"] > cutoff_time]
            
            # 按类型统计
            alert_types = {}
            severity_counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
            
            for alert in recent_alerts:
                alert_type = alert.get("type", "UNKNOWN")
                severity = alert.get("severity", "INFO")
                
                alert_types[alert_type] = alert_types.get(alert_type, 0) + 1
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            summary = {
                "time_range_hours": hours,
                "total_alerts": len(recent_alerts),
                "alert_types": alert_types,
                "severity_counts": severity_counts,
                "recent_alerts": recent_alerts[-5:] if recent_alerts else []  # 最近5个
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取警报摘要失败: {e}")
            return {"error": str(e)}
    
    def export_data(self, export_type: str = "all") -> Dict:
        """
        导出监控数据
        
        Args:
            export_type: 导出类型 ("performance", "risk", "alerts", "all")
            
        Returns:
            Dict: 导出的数据
        """
        try:
            export_data = {
                "export_time": time.time(),
                "export_datetime": datetime.now().isoformat(),
                "export_type": export_type
            }
            
            if export_type in ["performance", "all"]:
                export_data["performance_history"] = self.performance_history
            
            if export_type in ["risk", "all"]:
                export_data["risk_history"] = self.risk_history
            
            if export_type in ["alerts", "all"]:
                export_data["alert_history"] = self.alert_history
            
            return export_data
            
        except Exception as e:
            self.logger.error(f"导出数据失败: {e}")
            return {"error": str(e)}


class LoggingSystem:
    """日志系统"""
    
    @staticmethod
    def setup_logging(config: Dict[str, Any]) -> logging.Logger:
        """
        设置日志系统
        
        Args:
            config: 日志配置
            
        Returns:
            logging.Logger: 配置好的日志器
        """
        # 创建日志器
        logger = logging.getLogger("GridStrategy")
        logger.setLevel(getattr(logging, config.get("level", "INFO").upper()))
        
        # 清除现有处理器
        logger.handlers.clear()
        
        # 设置格式
        formatter = logging.Formatter(
            fmt=config.get("format", 
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            datefmt=config.get("date_format", "%Y-%m-%d %H:%M:%S")
        )
        
        # 控制台处理器
        if config.get("console", True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # 文件处理器
        if config.get("file_enabled", True):
            file_handler = logging.FileHandler(
                filename=config.get("file_path", "logs/grid_strategy.log"),
                mode="a",
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # 防止重复日志
        logger.propagate = False
        
        logger.info("日志系统初始化完成")
        return logger
    
    @staticmethod
    def create_trade_logger(config: Dict[str, Any]) -> logging.Logger:
        """
        创建交易专用日志器
        
        Args:
            config: 日志配置
            
        Returns:
            logging.Logger: 交易日志器
        """
        logger = logging.getLogger("GridStrategy.Trade")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        
        # 交易日志格式
        formatter = logging.Formatter(
            "%(asctime)s - TRADE - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 交易日志文件
        trade_handler = logging.FileHandler(
            filename=config.get("trade_log_path", "logs/trades.log"),
            mode="a",
            encoding="utf-8"
        )
        trade_handler.setFormatter(formatter)
        logger.addHandler(trade_handler)
        
        logger.propagate = False
        return logger
    
    @staticmethod
    def log_trade(logger: logging.Logger, trade_info: Dict):
        """
        记录交易信息
        
        Args:
            logger: 交易日志器
            trade_info: 交易信息
        """
        try:
            trade_msg = json.dumps(trade_info, ensure_ascii=False, default=str)
            logger.info(trade_msg)
        except Exception as e:
            logger.error(f"记录交易信息失败: {e}")
    
    @staticmethod
    def log_strategy_event(logger: logging.Logger, event_type: str, details: Dict):
        """
        记录策略事件
        
        Args:
            logger: 日志器
            event_type: 事件类型
            details: 事件详情
        """
        try:
            event_msg = f"{event_type}: {json.dumps(details, ensure_ascii=False, default=str)}"
            logger.info(event_msg)
        except Exception as e:
            logger.error(f"记录策略事件失败: {e}")
