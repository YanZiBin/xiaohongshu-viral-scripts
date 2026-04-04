# storage.py

import os
from datetime import datetime
from typing import List
import pandas as pd
from config import OUTPUT_CONFIG, CSV_FIELDS
from utils import setup_logger

logger = setup_logger("storage")


def create_output_dir(output_dir: str = None) -> str:
    """
    创建输出目录

    Args:
        output_dir: 输出目录路径

    Returns:
        创建的目录路径
    """
    if output_dir is None:
        output_dir = OUTPUT_CONFIG["OUTPUT_DIR"]

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info(f"创建输出目录：{output_dir}")

    return output_dir


def create_logs_dir(logs_dir: str = None) -> str:
    """
    创建日志目录

    Args:
        logs_dir: 日志目录路径

    Returns:
        创建的目录路径
    """
    if logs_dir is None:
        logs_dir = OUTPUT_CONFIG["LOGS_DIR"]

    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        logger.info(f"创建日志目录：{logs_dir}")

    return logs_dir


def save_to_csv(notes: List[dict], keyword: str, output_dir: str = None) -> str:
    """
    保存笔记数据到 CSV 文件

    Args:
        notes: 笔记数据列表
        keyword: 搜索关键词
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    if output_dir is None:
        output_dir = create_output_dir()

    # 生成文件名
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_CONFIG['FILE_PREFIX']}_{keyword}_{date_str}.csv"
    filepath = os.path.join(output_dir, filename)

    # 更新序号
    for i, note in enumerate(notes, 1):
        note["序号"] = i

    # 转换为 DataFrame
    df = pd.DataFrame(notes, columns=CSV_FIELDS)

    # 保存 CSV
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    logger.info(f"数据已保存到：{filepath}")

    return filepath


def save_to_excel(notes: List[dict], keyword: str, output_dir: str = None) -> str:
    """
    保存笔记数据到 Excel 文件

    Args:
        notes: 笔记数据列表
        keyword: 搜索关键词
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    if output_dir is None:
        output_dir = create_output_dir()

    # 生成文件名
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_CONFIG['FILE_PREFIX']}_{keyword}_{date_str}.xlsx"
    filepath = os.path.join(output_dir, filename)

    # 更新序号
    for i, note in enumerate(notes, 1):
        note["序号"] = i

    # 转换为 DataFrame
    df = pd.DataFrame(notes, columns=CSV_FIELDS)

    # 保存 Excel
    df.to_excel(filepath, index=False, engine="openpyxl")
    logger.info(f"数据已保存到：{filepath}")

    return filepath
