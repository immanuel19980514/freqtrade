import logging
import pandas as pd
from datetime import datetime
from copy import deepcopy
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import HTTPException

from freqtrade import __version__
from freqtrade.enums import RunMode, State
from freqtrade.exceptions import OperationalException
from freqtrade.rpc import RPC
from freqtrade.rpc.api_server.api_pairlists import handleExchangePayload
from freqtrade.rpc.api_server.api_schemas import (
    Health,
    Logs,
    MarketRequest,
    MarketResponse,
    Ping,
    PlotConfig,
    ShowConfig,
    StrategyResponse,
    SysInfo,
    Version,
    MacroCalendar,
    MacroCalendarEvent,
    NewsFlashEvent,
    NewsFlashResponse,
    SankeyNode,
    SankeyLink,
    MarketFactorResponse,
)
from freqtrade.rpc.api_server.deps import (
    get_config,
    get_exchange,
    get_rpc,
    get_rpc_optional,
    verify_strategy,
)
from freqtrade.rpc.rpc import RPCException

from freqtrade.rpc.api_server.akshare_utils import AkshareUtils
from freqtrade.rpc.api_server.news_flash_manager import get_news_manager
from freqtrade.rpc.api_server.market_factor_manager import MarketFactorManager

logger = logging.getLogger(__name__)

# API version
# Pre-1.1, no version was provided
# Version increments should happen in "small" steps (1.1, 1.12, ...) unless big changes happen.
# 1.11: forcebuy and forcesell accept ordertype
# 1.12: add blacklist delete endpoint
# 1.13: forcebuy supports stake_amount
# versions 2.xx -> futures/short branch
# 2.14: Add entry/exit orders to trade response
# 2.15: Add backtest history endpoints
# 2.16: Additional daily metrics
# 2.17: Forceentry - leverage, partial force_exit
# 2.20: Add websocket endpoints
# 2.21: Add new_candle messagetype
# 2.22: Add FreqAI to backtesting
# 2.23: Allow plot config request in webserver mode
# 2.24: Add cancel_open_order endpoint
# 2.25: Add several profit values to /status endpoint
# 2.26: increase /balance output
# 2.27: Add /trades/<id>/reload endpoint
# 2.28: Switch reload endpoint to Post
# 2.29: Add /exchanges endpoint
# 2.30: new /pairlists endpoint
# 2.31: new /backtest/history/ delete endpoint
# 2.32: new /backtest/history/ patch endpoint
# 2.33: Additional weekly/monthly metrics
# 2.34: new entries/exits/mix_tags endpoints
# 2.35: pair_candles and pair_history endpoints as Post variant
# 2.40: Add hyperopt-loss endpoint
# 2.41: Add download-data endpoint
# 2.42: Add /pair_history endpoint with live data
# 2.43: Add /profit_all endpoint
# 2.44: Add candle_types parameter to download-data endpoint
# 2.45: Add price to forceexit endpoint
# 2.46: Add prepend_data to download-data endpoint
# 2.47: Add Strategy parameters
# 2.48: add /backtest/history/wallets endpoint
# 2.49: Add /lookahead_analysis and /recursive_analysis endpoints and background job deletion
API_VERSION = 2.49

# Public API, requires no auth.
router_public = APIRouter()
# Private API, protected by authentication
router = APIRouter()


@router_public.get("/ping", response_model=Ping, tags=["Info"])
@router_public.head("/ping", response_model=Ping, tags=["Info"])
def ping():
    """simple ping to check if API is responsive

    Performs no internal checks, just returns pong.
    """
    return {"status": "pong"}


@router.get("/version", response_model=Version, tags=["Info"])
def version():
    """Bot Version info"""
    return {"version": __version__}


@router.get("/show_config", response_model=ShowConfig, tags=["Info"])
def show_config(rpc: RPC | None = Depends(get_rpc_optional), config=Depends(get_config)):
    state: State | str = ""
    strategy_version = None
    if rpc:
        state = rpc._freqtrade.state
        strategy_version = rpc._freqtrade.strategy.version()
    resp = RPC._rpc_show_config(config, state, strategy_version)
    resp["api_version"] = API_VERSION
    return resp


@router.get("/logs", response_model=Logs, tags=["Info"])
def logs(limit: int | None = None):
    return RPC._rpc_get_logs(limit)


@router.get("/plot_config", response_model=PlotConfig, tags=["Candle data"])
def plot_config(
    strategy: str | None = None,
    config=Depends(get_config),
    rpc: RPC | None = Depends(get_rpc_optional),
):
    if not strategy:
        if not rpc:
            raise RPCException("Strategy is mandatory in webserver mode.")
        return PlotConfig.model_validate(rpc._rpc_plot_config())
    else:
        config1 = deepcopy(config)
        config1.update({"strategy": strategy})
    try:
        return PlotConfig.model_validate(RPC._rpc_plot_config_with_strategy(config1))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/markets", response_model=MarketResponse, tags=["Candle data"])
def markets(
    query: Annotated[MarketRequest, Query()],
    config=Depends(get_config),
    rpc: RPC | None = Depends(get_rpc_optional),
):
    if not rpc or config["runmode"] == RunMode.WEBSERVER:
        # webserver mode
        config_loc = deepcopy(config)
        handleExchangePayload(query, config_loc)
        exchange = get_exchange(config_loc)
    else:
        exchange = rpc._freqtrade.exchange

    return {
        "markets": exchange.get_markets(
            base_currencies=[query.base] if query.base else None,
            quote_currencies=[query.quote] if query.quote else None,
            active_only=not query.include_inactive,
        ),
        "exchange_id": exchange.id,
    }


@router.get("/timeframes", tags=["Exchange"])
def get_timeframes(
    config=Depends(get_config),
    rpc: RPC | None = Depends(get_rpc_optional)
):
    """
    获取交易所支持的时间周期列表
    """
    if not rpc or config["runmode"] == RunMode.WEBSERVER:
        # webserver mode - 需要传入 exchange 参数
        # 可以从请求参数或配置中获取
        config_loc = deepcopy(config)
        exchange = get_exchange(config_loc)
    else:
        exchange = rpc._freqtrade.exchange
    
    return {
        "timeframes": exchange.timeframes,
        "exchange_id": exchange.id
    }



@router.get("/strategy/{strategy}", response_model=StrategyResponse, tags=["Strategy"])
def get_strategy(
    strategy: str, config=Depends(get_config), rpc: RPC | None = Depends(get_rpc_optional)
):
    verify_strategy(strategy)

    if not rpc or config["runmode"] == RunMode.WEBSERVER:
        # webserver mode
        config_ = deepcopy(config)
        from freqtrade.resolvers.strategy_resolver import StrategyResolver

        try:
            strategy_obj = StrategyResolver._load_strategy(
                strategy, config_, extra_dir=config_.get("strategy_path")
            )
            strategy_obj.ft_load_hyper_params()
        except OperationalException:
            raise HTTPException(status_code=404, detail="Strategy not found")
        except Exception:
            logger.exception("Unexpected error while loading strategy '%s'.", strategy)
            raise HTTPException(
                status_code=502,
                detail="Unexpected error while loading strategy.",
            )
    else:
        # trade mode
        strategy_obj = rpc._freqtrade.strategy
        if strategy_obj.get_strategy_name() != strategy:
            raise HTTPException(
                status_code=404,
                detail="Only the currently active strategy is available in trade mode",
            )
    return {
        "strategy": strategy_obj.get_strategy_name(),
        "timeframe": getattr(strategy_obj, "timeframe", None),
        "code": strategy_obj.__source__,
        "params": [p for _, p in strategy_obj.enumerate_parameters()],
    }


@router.get("/sysinfo", response_model=SysInfo, tags=["Info"])
def sysinfo():
    return RPC._rpc_sysinfo()


@router.get("/health", response_model=Health, tags=["Info"])
def health(rpc: RPC = Depends(get_rpc)):
    return rpc.health()

@router.get("/macro_calendar", response_model=MacroCalendar, tags=["Info"])
def macro_calendar(date: str = None):
    # 如果没有传入日期参数，使用当前日期
    if not date:
        date = datetime.now().strftime("%Y%m%d")
    
    # 获取指定日期的财经日历
    df = AkshareUtils.get_macro_calendar(date)

    # 打印数据（调试用）
    AkshareUtils.print_dataframe(df)

    # 将DataFrame转换为events列表
    events = []
    if not df.empty:
        for _, row in df.iterrows():
            # 辅助函数：处理nan值，转换为空字符串
            def get_value(key, default=""):
                val = row.get(key, default)
                # 检查是否为nan
                if pd.isna(val) or val is None:
                    return default
                return val
            
            event = {
                "date": str(get_value("日期", "")),
                "time": str(get_value("时间", "")),
                "country": str(get_value("地区", "")),
                "event": str(get_value("事件", "")),
                "event_name": "",
                "event_source": str(get_value("来源", "")),
                "importance": int(get_value("重要性", 0)),
                "actual": str(get_value("公布", "")),
                "forecast": str(get_value("预期", "")),
                "previous": str(get_value("前值", "")),
                "link": str(get_value("链接", "")),
                "impact": "",
            }
            events.append(event)

    res: dict[str, None | str | int | list] = {
        "date": date,
        "total": len(df),
        "events": events,
    }

    return res


@router.get("/news_flash", response_model=NewsFlashResponse, tags=["Info"])
def news_flash(hour_key: str = None, refresh: bool = False):
    """
    获取新闻快讯数据
    
    参数:
        hour_key: 小时标识，格式如 "YYYY-MM-DD HH:00:00"，为空则使用当前时间
        
    返回:
        NewsFlashResponse: 包含新闻快讯列表和统计信息
    """
    # 获取NewsFlashManager实例
    manager = get_news_manager()

    run_task_now = False;
    
    # 检查是否启动，如果没有则启动
    if not manager.running:
        logger.info("NewsFlashManager未启动，正在启动...")
        manager.start()

        # 立即执行一次任务
        manager.run_task_now()
        run_task_now = True
    
    # 如果hour_key为空，设置为当前时间，并立即执行一次任务
    if not hour_key:
        hour_key = datetime.now().strftime("%Y-%m-%d %H:00:00")
        logger.info(f"hour_key为空，已设置为当前时间: {hour_key}，立即执行一次任务")
        # 立即执行一次任务
        if not run_task_now:
            manager.run_task_now()
            run_task_now = True

    if refresh and not run_task_now:
        manager.run_task_now()
        run_task_now = True
    
    # 获取指定小时的数据
    df = manager.get_hour_data(hour_key)
    
    # 打印数据（调试用）
    if not df.empty:
        AkshareUtils.print_dataframe(df, title=f"新闻快讯 - {hour_key}")
    
    # 将DataFrame转换为events列表
    events = []
    if not df.empty:
        for _, row in df.iterrows():
            # 辅助函数：处理nan值，转换为空字符串
            def get_value(key, default=""):
                val = row.get(key, default)
                # 检查是否为nan
                if pd.isna(val) or val is None:
                    return default
                return str(val)
            
            event = NewsFlashEvent(
                title=get_value("标题", ""),
                content=get_value("内容", ""),
                date=get_value("发布日期", ""),
                time=get_value("发布时间", ""),
                link=get_value("链接", ""),
                source=get_value("来源", ""),
            )
            events.append(event)
    
    res = NewsFlashResponse(
        news=events,
        hour_key=hour_key,
        total=len(events),
    )
    
    logger.info(f"返回 {len(events)} 条新闻快讯数据 (hour_key: {hour_key})")
    
    return res


@router.get("/market_factor", response_model=MarketFactorResponse, tags=["Info"])
def market_factor(refresh: bool = False):
    """
    获取市场因素桑基图数据
    
    Args:
        refresh: 是否强制从文件刷新数据，默认False使用缓存
    
    返回:
        MarketFactorResponse: 包含桑基图节点和链接数据
    """
    # 获取因素列表和因素关系
    factors_df = MarketFactorManager.get_factors(refresh=refresh)
    relations_df = MarketFactorManager.get_factor_relations(refresh=refresh)
    
    # 构建节点集合（包含所有因素名称）
    node_names = set()
    
    # 从因素列表获取所有因素名称
    if "名称" in factors_df.columns:
        for name in factors_df["名称"]:
            if factors_df["状态"] == "1":
                node_names.add(str(name))

    # 构建节点列表
    nodes = []
    if not factors_df.empty:
        for _, row in factors_df.iterrows():
            if row["状态"] == "1":
                name = str(row.get("名称", ""))
                description = str(row.get("说明", ""))
                itemStyle = {"borderWidth": 1}

                category = str(row.get("分类", ""))
                country = str(row.get("国家", ""))

                if category:
                    itemStyle["color"] = MarketFactorManager.get_category_color(category)

                if country:
                    itemStyle["borderColor"] = MarketFactorManager.get_country_color(country)

                if name :
                    nodes.append(SankeyNode(
                        name=name,
                        category=category,
                        country=country,
                        description=description,
                        itemStyle=itemStyle
                    ))



    # 构建链接列表
    links = []
    if not relations_df.empty:
        for _, row in relations_df.iterrows():
            source = str(row.get("源头因素", ""))
            target = str(row.get("结果因素", ""))
            weight = int(row.get("权重", 1))
            description = str(row.get("说明", ""))
            impact = str(row.get("影响", ""))

            lineStyle = {}

            if impact and impact == "利空":
                lineStyle["color"] = "#FF0000"
            elif impact and impact == "利多":
                lineStyle["color"] = "#00FF00"

            if source and target and source in node_names and target in node_names:
                links.append(SankeyLink(
                    source=source,
                    target=target,
                    value=weight,
                    description=description,
                    lineStyle=lineStyle,
                ))

    logger.info(f"返回桑基图数据：{len(nodes)} 个节点，{len(links)} 条链接")

    return MarketFactorResponse(
        nodes=nodes,
        links=links
    )
