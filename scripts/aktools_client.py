#!/usr/bin/env python3
"""
aktools Client - Python version
通过HTTP请求访问aktools API服务，获取JSON数据并转换为DataFrame

使用方法:  macro_china_cpi  macro_china_gdp

    python scripts/aktools_client.py --uri macro_china_cpi?key=123456 --desc 月份
    python scripts/aktools_client.py --uri macro_china_cpi?key=123456 --limit 10 --columns "月份,全国-当月,全国-同比增长" --asc 月份 --desc 地区

"""

import argparse
import sys
from datetime import datetime

try:
    import requests
    import pandas as pd
except ImportError:
    print("Error: requests or pandas not installed.")
    print("Please install them with: pip install requests pandas")
    sys.exit(1)


# 默认API服务地址
DEFAULT_API_BASE = "http://aktools.mcvey.cn/api/public/"


def get_data_from_api(
    uri: str,
    api_base: str = DEFAULT_API_BASE,
    **kwargs
) -> pd.DataFrame:
    """
    通过HTTP GET请求访问aktools API，获取JSON数据并转换为DataFrame
    
    Args:
        uri: 数据URI标识（如 stock_zh_a_hist）
        api_base: API服务基础地址
        
    Returns:
        pd.DataFrame: 获取到的数据
        

    """
    # 构建完整URL
    url = f"{api_base}{uri}"
    
    print(f"正在请求: {url}")

    
    try:
        # 发送HTTP GET请求（类似R的getForm）
        response = requests.get(
            url,
            params=kwargs,
            headers={"Accept": "application/json"},
            timeout=30
        )
        
        # 检查响应状态
        if response.status_code != 200:
            print(f"Error: HTTP请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
            return pd.DataFrame()
        
        # 解析JSON数据（类似R的fromJSON）
        json_data = response.json()
        
        # 转换为DataFrame
        if isinstance(json_data, list):
            df = pd.DataFrame(json_data)
        elif isinstance(json_data, dict):
            # 如果是字典，尝试直接转换或提取数据字段
            if "data" in json_data:
                df = pd.DataFrame(json_data["data"])
            else:
                df = pd.DataFrame([json_data])
        else:
            print(f"Error: 无法解析的JSON格式: {type(json_data)}")
            return pd.DataFrame()
        
        print(f"成功获取 {len(df)} 条数据")
        return df
        
    except requests.exceptions.ConnectionError as e:
        print(f"Error: 无法连接到API服务 {api_base}")
        print(f"请确认aktools服务是否已启动")
        print(f"连接错误: {e}")
        return pd.DataFrame()
    except requests.exceptions.Timeout as e:
        print(f"Error: 请求超时: {e}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        print(f"Error: 请求异常: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error: 数据处理异常: {e}")
        return pd.DataFrame()


def print_dataframe(df: pd.DataFrame, title: str = "数据", columns: list = None):
    """
    格式化打印 DataFrame
    
    Args:
        df: 要打印的 DataFrame
        title: 标题
        columns: 要显示的列名列表（None表示显示所有列）
    """
    if df.empty:
        print(f"{title}: 无数据")
        return
    
    # 如果指定了列，过滤DataFrame
    if columns and len(columns) > 0:
        # 检查列是否存在
        valid_columns = []
        invalid_columns = []
        for col in columns:
            if col in df.columns:
                valid_columns.append(col)
            else:
                invalid_columns.append(col)
        
        # 打印无效列警告
        if invalid_columns:
            print(f"警告: 以下列不存在于数据中，将被忽略: {invalid_columns}")
            print(f"可用列: {list(df.columns)}")
        
        if valid_columns:
            df = df[valid_columns]
        else:
            print("警告: 没有有效的列名，将显示所有列")
    
    print("\n" + "=" * 80)
    print(f"{title}")
    print("=" * 80)
    
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 50)
    
    print(df.to_string())
    print("\n" + "=" * 80)
    print(f"列名: {list(df.columns)}")
    print(f"数据行数: {len(df)}")


def main():
    """
    主函数 - 命令行入口
    """
    parser = argparse.ArgumentParser(
        description="aktools Client - Python version (HTTP API方式)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        
    )
    
    parser.add_argument(
        "--uri",
        type=str,
        help="数据URI标识（如 stock_zh_a_hist, macro_china_cpi）"
    )
    
    parser.add_argument(
        "--api_base",
        type=str,
        default=DEFAULT_API_BASE,
        help=f"API服务基础地址 (默认: {DEFAULT_API_BASE})"
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
        help="导出数据到 CSV 文件路径"
    )
    
    parser.add_argument(
        "--columns",
        type=str,
        default=None,
        help="指定要显示的列名，用逗号分隔，如: --columns '全国-当月,城市-当月'"
    )
    
    parser.add_argument(
        "--desc",
        type=str,
        default=None,
        help="指定按哪个字段倒序排序，如: --desc 月份"
    )
    
    parser.add_argument(
        "--asc",
        type=str,
        default=None,
        help="指定按哪个字段升序排序，如: --asc 名称"
    )
    
    args = parser.parse_args()
    

    
    # 必须指定URI
    if not args.uri:
        print("Error: 请使用 --uri 参数指定数据URI")
        print("使用 --list 查看所有常用URI")
        sys.exit(1)
    
    print(f"\naktools Client (HTTP API) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)
    
    # 构建请求参数
    params = {}

    
    # 通过HTTP请求获取数据
    df = get_data_from_api(
        uri=args.uri,
        api_base=args.api_base,
        **params
    )
    
    # 按指定字段排序（支持同时使用 --desc 和 --asc）
    if not df.empty:
        sort_columns = []
        sort_orders = []
        
        if args.desc:
            if args.desc in df.columns:
                sort_columns.append(args.desc)
                sort_orders.append(False)  # False = 倒序
                print(f"按 '{args.desc}' 倒序排序")
            else:
                print(f"警告: 排序字段 '{args.desc}' 不存在于数据中，跳过排序")
                print(f"可用字段: {list(df.columns)}")
        
        if args.asc:
            if args.asc in df.columns:
                sort_columns.append(args.asc)
                sort_orders.append(True)  # True = 升序
                print(f"按 '{args.asc}' 升序排序")
            else:
                print(f"警告: 排序字段 '{args.asc}' 不存在于数据中，跳过排序")
                print(f"可用字段: {list(df.columns)}")
        
        if sort_columns:
            df = df.sort_values(by=sort_columns, ascending=sort_orders)
    
    # 应用行数限制
    if args.limit and not df.empty:
        df = df.head(args.limit)
    
    # 解析 columns 参数
    selected_columns = None
    if args.columns:
        # 按逗号分隔，去除前后空格
        selected_columns = [col.strip() for col in args.columns.split(",")]
        print(f"指定显示列: {selected_columns}")
    
    # 打印数据
    print_dataframe(df, args.uri, columns=selected_columns)
    
    # 导出数据
    if args.export and not df.empty:
        filename = f"{args.export}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"\n数据已导出到: {filename}")
    
    print("\n完成!")


if __name__ == "__main__":
    main()