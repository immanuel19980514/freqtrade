#!/usr/bin/env python3
"""
Macro Calendar Data Fetcher
获取美国和中国的宏观数据，通过 akshare 的各种 macro 接口

使用方法:
    python scripts/macro_calendar.py --list
    python scripts/macro_calendar.py --calendar

    python scripts/macro_calendar.py --country us
    python scripts/macro_calendar.py --country us
    python scripts/macro_calendar.py --country cn
    python scripts/macro_calendar.py --indicator cpi

    python scripts/macro_calendar.py --limit 10
    python scripts/macro_calendar.py --export data
"""

import argparse
import sys
from datetime import datetime

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print("Error: akshare or pandas not installed.")
    print("Please install them with: pip install akshare pandas")
    sys.exit(1)


# 定义可获取的宏观数据指标
US_INDICATORS = {
    "cpi": {"func": "macro_usa_cpi_yoy", "desc": "美国CPI同比"},
    "cpi_monthly": {"func": "macro_usa_cpi_monthly", "desc": "美国CPI月度"},
    "gdp": {"func": "macro_usa_gdp_monthly", "desc": "美国GDP月度"},
    "non_farm": {"func": "macro_usa_non_farm", "desc": "美国非农就业数据"},
    "unemployment": {"func": "macro_usa_unemployment_rate", "desc": "美国失业率"},
    "pmi": {"func": "macro_usa_pmi", "desc": "美国PMI"},
    "retail_sales": {"func": "macro_usa_retail_sales", "desc": "美国零售销售"},
    "interest_rate": {"func": "macro_bank_usa_interest_rate", "desc": "美国利率"},
}

CN_INDICATORS = {
    "cpi": {"func": "macro_china_cpi", "desc": "中国CPI"},
    "cpi_monthly": {"func": "macro_china_cpi_monthly", "desc": "中国CPI月度"},
    "gdp": {"func": "macro_china_gdp", "desc": "中国GDP"},
    "gdp_yearly": {"func": "macro_china_gdp_yearly", "desc": "中国GDP年度"},
    "pmi": {"func": "macro_china_cx_pmi_yearly", "desc": "中国PMI"},
    "m2": {"func": "macro_china_m2_yearly", "desc": "中国M2货币供应"},
    "lpr": {"func": "macro_china_lpr", "desc": "中国LPR利率"},
    "interest_rate": {"func": "macro_bank_china_interest_rate", "desc": "中国利率"},
}

def get_func(func_name: str) -> callable:

    return getattr(ak, func_name)


def get_macro_data(country: str, indicator: str) -> pd.DataFrame:
    """
    获取宏观数据
    
    Args:
        country: 国家代码 (us/cn)
        indicator: 指标名称
        
    Returns:
        pd.DataFrame: 宏观数据
    """
    indicators = US_INDICATORS if country == "us" else CN_INDICATORS
    
    if indicator not in indicators:
        print(f"Error: 不支持的指标 '{indicator}'")
        print(f"支持的指标: {list(indicators.keys())}")
        return pd.DataFrame()
    
    func_name = indicators[indicator]["func"]
    desc = indicators[indicator]["desc"]
    
    print(f"正在获取 {desc}...")
    
    try:
        func = get_func(func_name)
        df = func()
        print(f"获取到 {len(df)} 条数据")
        return df
    except Exception as e:
        print(f"获取数据失败: {e}")
        return pd.DataFrame()


def get_all_macro_data(country: str) -> dict[str, pd.DataFrame]:
    """
    获取指定国家的所有宏观数据
    
    Args:
        country: 国家代码 (us/cn)
        
    Returns:
        dict: 指标名称到 DataFrame 的映射
    """
    indicators = US_INDICATORS if country == "us" else CN_INDICATORS
    results = {}
    
    for indicator, info in indicators.items():
        df = get_macro_data(country, indicator)
        if not df.empty:
            results[indicator] = df
    
    return results


def print_dataframe(df: pd.DataFrame, title: str = "宏观数据"):
    """
    格式化打印 DataFrame
    
    Args:
        df: 要打印的 DataFrame
        title: 标题
    """
    if df.empty:
        print(f"{title}: 无数据")
        return
    
    print("\n" + "=" * 80)
    print(f"{title}")
    print("=" * 80)
    
    # 设置 pandas 显示选项
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 50)
    
    # 打印 DataFrame
    print(df.to_string())
    print("\n" + "=" * 80)
    
    # 打印列信息
    print(f"\n列名: {list(df.columns)}")
    print(f"数据行数: {len(df)}")

def list_calendar():
    """获取金十全球宏观日历，筛选中美欧核心数据"""
    df_ak = ak.macro_calendar()
    # 转换时间格式
    df_ak["date"] = pd.to_datetime(df_ak["date"])
    # 筛选目标地区
    target_area = ["美国", "中国", "欧元区", "德国", "法国"]
    df_ak = df_ak[df_ak["country"].isin(target_area)].copy()
    # 保留核心字段并重命名
    df_ak = df_ak[["date", "country", "indicator", "previous", "forecast", "actual", "importance"]]
    df_ak.rename(
        columns={
            "date": "发布时间",
            "country": "国家/地区",
            "indicator": "指标名称",
            "previous": "前值",
            "forecast": "预期值",
            "actual": "实际值"
        },
        inplace=True
    )
    df_ak["数据来源"] = "AkShare(金十)"
    print_dataframe(df_ak, "金十全球宏观日历")



def list_available_indicators():
    """
    列出所有可用的指标
    """
    print("\n" + "=" * 80)
    print("可用的宏观数据指标")
    print("=" * 80)
    
    print("\n美国指标:")
    for indicator, info in US_INDICATORS.items():
        print(f"  {indicator}: {info['desc']}")
    
    print("\n中国指标:")
    for indicator, info in CN_INDICATORS.items():
        print(f"  {indicator}: {info['desc']}")
    
    print("\n" + "=" * 80)


def main():
    """
    主函数 - 命令行入口
    """
    parser = argparse.ArgumentParser(
        description="获取美国和中国的宏观数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/macro_calendar.py --list              # 列出所有可用指标
    python scripts/macro_calendar.py --country us        # 获取美国所有宏观数据
    python scripts/macro_calendar.py --country cn        # 获取中国所有宏观数据
    python scripts/macro_calendar.py --country us --indicator cpi  # 获取美国CPI
    python scripts/macro_calendar.py --country cn --indicator gdp  # 获取中国GDP
    python scripts/macro_calendar.py --export macro_data # 导出数据到CSV
        """
    )
    
    parser.add_argument(
        "--country",
        type=str,
        default="all",
        choices=["us", "cn", "all"],
        help="选择国家: us(美国), cn(中国), all(所有)"
    )
    
    parser.add_argument(
        "--indicator",
        type=str,
        default=None,
        help="指定指标名称，如 cpi, gdp, pmi 等"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制显示的数据行数"
    )

    
    
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="导出数据到 CSV 文件路径前缀"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的指标"
    )
    
    parser.add_argument(
        "--calendar",
        action="store_true",
        help="获取金十全球宏观日历，筛选中美欧核心数据"
    )
    
    args = parser.parse_args()
    
    # 列出可用指标
    if args.list:
        list_available_indicators()
        return

    if args.calendar:
        list_calendar()
        return
    
    print(f"\n宏观数据获取工具 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)
    
    # 获取特定指标
    if args.indicator:
        if args.country == "all":
            # 获取两个国家的同一指标
            df_us = get_macro_data("us", args.indicator)
            df_cn = get_macro_data("cn", args.indicator)
            
            if args.limit:
                df_us = df_us.head(args.limit) if not df_us.empty else df_us
                df_cn = df_cn.head(args.limit) if not df_cn.empty else df_cn
            
            print_dataframe(df_us, f"美国 {args.indicator}")
            print_dataframe(df_cn, f"中国 {args.indicator}")
            
            if args.export:
                if not df_us.empty:
                    df_us.to_csv(f"{args.export}_us_{args.indicator}.csv", index=False, encoding="utf-8-sig")
                    print(f"美国数据已导出到: {args.export}_us_{args.indicator}.csv")
                if not df_cn.empty:
                    df_cn.to_csv(f"{args.export}_cn_{args.indicator}.csv", index=False, encoding="utf-8-sig")
                    print(f"中国数据已导出到: {args.export}_cn_{args.indicator}.csv")
        else:
            df = get_macro_data(args.country, args.indicator)
            if args.limit:
                df = df.head(args.limit) if not df.empty else df
            print_dataframe(df, f"{args.country} {args.indicator}")
            
            if args.export:
                df.to_csv(f"{args.export}_{args.country}_{args.indicator}.csv", index=False, encoding="utf-8-sig")
                print(f"数据已导出到: {args.export}_{args.country}_{args.indicator}.csv")
    
    # 获取所有指标
    else:
        if args.country == "all":
            us_data = get_all_macro_data("us")
            cn_data = get_all_macro_data("cn")
            
            for indicator, df in us_data.items():
                if args.limit:
                    df = df.head(args.limit)
                print_dataframe(df, f"美国 {US_INDICATORS[indicator]['desc']}")
                
                if args.export:
                    df.to_csv(f"{args.export}_us_{indicator}.csv", index=False, encoding="utf-8-sig")
            
            for indicator, df in cn_data.items():
                if args.limit:
                    df = df.head(args.limit)
                print_dataframe(df, f"中国 {CN_INDICATORS[indicator]['desc']}")
                
                if args.export:
                    df.to_csv(f"{args.export}_cn_{indicator}.csv", index=False, encoding="utf-8-sig")
        
        elif args.country == "us":
            us_data = get_all_macro_data("us")
            for indicator, df in us_data.items():
                if args.limit:
                    df = df.head(args.limit)
                print_dataframe(df, f"美国 {US_INDICATORS[indicator]['desc']}")
                
                if args.export:
                    df.to_csv(f"{args.export}_us_{indicator}.csv", index=False, encoding="utf-8-sig")
        
        elif args.country == "cn":
            cn_data = get_all_macro_data("cn")
            for indicator, df in cn_data.items():
                if args.limit:
                    df = df.head(args.limit)
                print_dataframe(df, f"中国 {CN_INDICATORS[indicator]['desc']}")
                
                if args.export:
                    df.to_csv(f"{args.export}_cn_{indicator}.csv", index=False, encoding="utf-8-sig")
    
    print("\n完成!")


if __name__ == "__main__":
    main()