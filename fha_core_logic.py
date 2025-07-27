# fha_core_logic.py
# -*- coding: utf-8 -*-
# 职责：整合所有后端数据模型、业务逻辑和数据处理功能。

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QColor, QBrush

# ------------------- 失效模式知识库 -------------------
FAILURE_MODE_LIBRARY = {
    "通用": ["功能完全丧失", "功能间歇性工作", "功能性能下降", "功能非预期启动"],
    "传感器": ["持续输出错误信息", "输出数据冻结/卡死", "数据跳变/噪声过大", "输出数据延迟"],
    "数据传输": ["数据包丢失", "数据完整性破坏 (误码)", "通信中断"],
    "执行机构": ["无响应/卡死", "响应延迟/迟钝", "动作超调/不到位", "反向运动"],
    "电源": ["电压/电流异常", "供电中断"],
    "导航": ["定位精度下降", "航向错误", "速度信息错误"],
    "飞控算法": ["算法发散", "模式切换错误"]
}


# ------------------- FHA核心数据模型 -------------------
class FHA_Model:
    """FHA功能的数据模型，负责所有数据操作。"""
    TABLE_COLUMNS = [
        '编号', '一级功能', '二级功能', '三级功能', '功能类型', '飞行阶段',
        '失效状态',
        '对于飞行器的影响', '对于地面/空域的影响', '对于地面控制组的影响',
        '危害性分类', '理由/备注',
    ]
    ARP4761_CATEGORIES = [
        "",  # 允许为空
        "灾难的 (Catastrophic)", "危险的 (Hazardous)", "严重的 (Major)",
        "轻微的 (Minor)", "无安全影响 (No Safety Effect)"
    ]

    def __init__(self):
        self.dataframe = self.new_blank_dataframe()
        self.next_id = 1

    def get_dataframe(self):
        return self.dataframe

    def new_blank_dataframe(self):
        return pd.DataFrame(columns=self.TABLE_COLUMNS)

    def new_project(self):
        self.dataframe = self.new_blank_dataframe()
        self.next_id = 1

    def load_dataframe(self, df):
        self.dataframe = df.reindex(columns=self.TABLE_COLUMNS).fillna('')
        if not self.dataframe.empty and '编号' in self.dataframe.columns:
            numeric_ids = self.dataframe['编号'].str.replace(r'\D', '', regex=True)
            numeric_ids = pd.to_numeric(numeric_ids, errors='coerce').dropna()
            self.next_id = int(numeric_ids.max()) + 1 if not numeric_ids.empty else 1
        else:
            self.next_id = 1

    def add_fha_entries(self, entries_list):
        if not entries_list:
            return
        new_rows = []
        for entry in entries_list:
            entry_copy = {k: entry.get(k, '') for k in self.TABLE_COLUMNS}
            new_rows.append(entry_copy)

        new_df = pd.DataFrame(new_rows, columns=self.TABLE_COLUMNS)
        self.dataframe = pd.concat([self.dataframe, new_df], ignore_index=True)
        self.re_number_ids()

    def update_fha_entries_from_wizard(self, source_index, wizard_results):
        if not wizard_results:
            return

        source_row_data = self.dataframe.loc[source_index].copy()

        df_before = self.dataframe.iloc[:source_index]
        df_after = self.dataframe.iloc[source_index + 1:]

        updated_entries = []
        for result in wizard_results:
            new_entry = source_row_data.copy()
            new_entry.update(result)
            updated_entries.append(new_entry)

        df_updated = pd.DataFrame(updated_entries, columns=self.TABLE_COLUMNS)

        self.dataframe = pd.concat([df_before, df_updated, df_after], ignore_index=True)
        self.re_number_ids()

    def delete_rows(self, row_indices):
        if not row_indices: return
        self.dataframe.drop(row_indices, inplace=True)
        self.dataframe.reset_index(drop=True, inplace=True)
        self.re_number_ids()

    def re_number_ids(self):
        """重新为所有行生成连续的编号"""
        for i in range(len(self.dataframe)):
            self.dataframe.loc[i, '编号'] = f"FHA-{i + 1:03d}"
        self.next_id = len(self.dataframe) + 1


# ------------------- Pandas-Qt表格适配器 -------------------
class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return len(self._data.index)

    def columnCount(self, parent=QModelIndex()):
        return len(self._data.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return str(self._data.iloc[index.row(), index.column()])
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(self._data.iloc[index.row(), index.column()])
        if role == Qt.ItemDataRole.BackgroundRole:
            if '失效状态' in self._data.columns and (
                    pd.isna(self._data.iloc[index.row()]['失效状态']) or self._data.iloc[index.row()][
                '失效状态'] == ''):
                return QColor("#FFF9C4")
            return QColor("#FFFFFF") if index.row() % 2 == 0 else QColor("#F8F8F8")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self._data.columns[section]
            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section] + 1)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.EditRole:
            self._data.iloc[index.row(), index.column()] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable


# ------------------- Excel导入导出功能 -------------------
def import_from_excel(filepath):
    try:
        df = pd.read_excel(filepath, engine='openpyxl').fillna('').astype(str)
        return df, "加载成功！"
    except Exception as e:
        return None, f"加载失败: {e}"


def export_to_excel(dataframe, filepath):
    if dataframe.empty:
        return False, "没有可导出的数据。"
    try:
        dataframe.to_excel(filepath, index=False, engine='openpyxl')
        return True, f"报告已成功导出至\n{filepath}"
    except Exception as e:
        return False, f"导出失败: {e}"