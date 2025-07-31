# fha_main_window.py
# -*- coding: utf-8 -*-
# 职责：应用主入口和所有UI组件的集合，是提供给外部集成的核心。

import sys
import pandas as pd
import numpy as np  # 导入 numpy 用于旭日图计算
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QMessageBox, QFileDialog, QTabWidget, QToolBar, QStatusBar, QDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QCheckBox,
    QAbstractItemView, QPushButton, QDialogButtonBox, QLabel, QHeaderView,
    QLineEdit, QComboBox, QWizard, QWizardPage, QListWidget, QTextEdit,
    QFormLayout, QSplitter, QStyledItemDelegate, QFrame
)
from PySide6.QtGui import QAction, QIcon, QColor, QBrush, QFont
from PySide6.QtCore import Qt

# 从后端核心逻辑模块导入所需类和函数
from fha_core_logic import FHA_Model, PandasModel, import_from_excel, export_to_excel, FAILURE_MODE_LIBRARY

# Matplotlib 用于仪表盘绘图
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches  # 导入用于创建图例

plt.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体为黑体
plt.rcParams['axes.unicode_minus'] = False  # 解决保存图像是负号'-'显示为方块的问题


# ------------------- 表格内下拉框委托 -------------------
class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.items)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


# ------------------- 功能架构与任务剖析模块 -------------------
class FunctionalArchitectDialog(QDialog):
    MISSION_PHASES = ["地面检查", "启动", "垂直起飞", "过渡飞行", "巡航", "悬停作业", "返航", "垂直降落", "关机"]
    FUNCTION_TYPES = ["电源", "传感器", "执行机构", "数据传输", "飞控算法", "导航", "通信", "其他"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建FHA项目 - 功能架构与任务剖析向导")
        self.setMinimumSize(1000, 700)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        func_layout = QHBoxLayout()
        self.func_name_input = QLineEdit()
        self.func_name_input.setPlaceholderText("输入功能名称...")
        self.func_type_combo = QComboBox()
        self.func_type_combo.addItems(self.FUNCTION_TYPES)
        self.add_func_button = QPushButton("添加顶层功能")
        self.add_sub_func_button = QPushButton("添加子功能")
        self.delete_func_button = QPushButton("删除选中")

        func_layout.addWidget(QLabel("功能名:"))
        func_layout.addWidget(self.func_name_input)
        func_layout.addWidget(QLabel("功能类型:"))
        func_layout.addWidget(self.func_type_combo)
        func_layout.addWidget(self.add_func_button)
        func_layout.addWidget(self.add_sub_func_button)
        func_layout.addWidget(self.delete_func_button)

        content_layout = QHBoxLayout()
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["功能架构", "类型"])
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.matrix_table = QTableWidget()
        self.matrix_table.setColumnCount(len(self.MISSION_PHASES))
        self.matrix_table.setHorizontalHeaderLabels(self.MISSION_PHASES)

        content_layout.addWidget(self.tree_widget, 1)
        content_layout.addWidget(self.matrix_table, 2)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_layout.addLayout(func_layout)
        main_layout.addLayout(content_layout)
        main_layout.addWidget(button_box)

        self.add_func_button.clicked.connect(self.add_top_level_function)
        self.add_sub_func_button.clicked.connect(self.add_sub_function)
        self.delete_func_button.clicked.connect(self.delete_function)
        self.tree_widget.itemSelectionChanged.connect(self.update_matrix)

    def add_top_level_function(self):
        func_name = self.func_name_input.text().strip()
        if not func_name: QMessageBox.warning(self, "警告", "功能名称不能为空！"); return
        item = QTreeWidgetItem(self.tree_widget, [func_name, self.func_type_combo.currentText()])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.func_name_input.clear()
        self.update_matrix()

    def add_sub_function(self):
        selected_item = self.tree_widget.currentItem()
        if not selected_item: QMessageBox.information(self, "提示", "请先在左侧的功能树中选择一个父功能。"); return
        func_name = self.func_name_input.text().strip()
        if not func_name: QMessageBox.warning(self, "警告", "功能名称不能为空！"); return
        item = QTreeWidgetItem(selected_item, [func_name, self.func_type_combo.currentText()])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        selected_item.setExpanded(True);
        self.func_name_input.clear()
        self.update_matrix()

    def delete_function(self):
        selected_item = self.tree_widget.currentItem()
        if selected_item:
            (selected_item.parent() or self.tree_widget.invisibleRootItem()).removeChild(selected_item)
            self.update_matrix()

    def update_matrix(self):
        self.matrix_table.setRowCount(0)
        leaf_items = self._find_leaf_items(self.tree_widget.invisibleRootItem())
        self.matrix_table.setRowCount(len(leaf_items))
        self.matrix_table.setVerticalHeaderLabels([self._get_full_path(item) for item in leaf_items])
        self.matrix_table.item_mapping = {r: item for r, item in enumerate(leaf_items)}
        for r, item in enumerate(leaf_items):
            for c in range(len(self.MISSION_PHASES)):
                checkbox = QCheckBox()
                cell_widget = QWidget();
                layout = QHBoxLayout(cell_widget)
                layout.addWidget(checkbox);
                layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.setContentsMargins(0, 0, 0, 0)
                self.matrix_table.setCellWidget(r, c, cell_widget)

    def _find_leaf_items(self, parent_item):
        leaves = []
        if parent_item.childCount() == 0 and parent_item != self.tree_widget.invisibleRootItem(): return [parent_item]
        for i in range(parent_item.childCount()): leaves.extend(self._find_leaf_items(parent_item.child(i)))
        return leaves

    def _get_full_path(self, item):
        path = [];
        while item: path.insert(0, item.text(0)); item = item.parent()
        return " / ".join(path)

    def get_fha_skeleton(self):
        skeleton = []
        if not hasattr(self.matrix_table, 'item_mapping'): return []
        for r, item in self.matrix_table.item_mapping.items():
            for c, phase in enumerate(self.MISSION_PHASES):
                checkbox = self.matrix_table.cellWidget(r, c).findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    path = self._get_full_path(item).split(' / ')
                    skeleton.append({
                        '一级功能': path[0] if len(path) > 0 else '', '二级功能': path[1] if len(path) > 1 else '',
                        '三级功能': path[2] if len(path) > 2 else '', '功能类型': item.text(1), '飞行阶段': phase,
                    })
        return skeleton


# ------------------- 引导式分析向导模块 -------------------
class AnalysisWizard(QWizard):
    def __init__(self, fha_row_data, parent=None):
        super().__init__(parent)
        self.fha_row_data = fha_row_data
        self.analysis_data = {"selected_modes": [], "effects": [], "hazards": []}
        self.final_results = []
        self.addPage(SelectFailureModesPage(self))
        self.addPage(AnalyzeEffectsPage(self))
        self.addPage(AssessHazardPage(self))
        self.setWindowTitle("引导式失效分析向导")


class BaseAnalysisPage(QWizardPage):
    def __init__(self, wizard, parent=None):
        super().__init__(parent)
        self.wizard = wizard


class SelectFailureModesPage(BaseAnalysisPage):
    def __init__(self, wizard, parent=None):
        super().__init__(wizard, parent)
        self.setTitle("第一步：选择失效模式")
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        func_type = self.wizard.fha_row_data.get('功能类型', '通用')
        modes = sorted(list(set(FAILURE_MODE_LIBRARY.get("通用", [])) | set(FAILURE_MODE_LIBRARY.get(func_type, []))))
        self.list_widget.addItems(modes)
        layout.addWidget(self.list_widget)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self):
        self.wizard.analysis_data['selected_modes'] = [item.text() for item in self.list_widget.selectedItems()]
        self.completeChanged.emit()

    def isComplete(self):
        return bool(self.wizard.analysis_data.get('selected_modes'))


class AnalyzeEffectsPage(BaseAnalysisPage):
    def __init__(self, wizard, parent=None):
        super().__init__(wizard, parent)
        self.current_mode_index = 0
        layout = QFormLayout(self)
        self.title_label = QLabel()
        self.aircraft_effect_edit = QTextEdit()
        self.airspace_effect_edit = QTextEdit()
        self.gcs_effect_edit = QTextEdit()
        layout.addRow(self.title_label);
        layout.addRow("对于飞行器的影响:", self.aircraft_effect_edit)
        layout.addRow("对于地面/空域的影响:", self.airspace_effect_edit);
        layout.addRow("对于地面控制组的影响:", self.gcs_effect_edit)

    def initializePage(self):
        self.current_mode_index = 0
        self.wizard.analysis_data['effects'] = [["", "", ""] for _ in self.wizard.analysis_data['selected_modes']]
        if self.wizard.analysis_data['selected_modes']: self.update_ui_for_current_mode()

    def validatePage(self):
        self._save_current_effects()
        if self.current_mode_index < len(self.wizard.analysis_data['selected_modes']) - 1:
            self.current_mode_index += 1;
            self.update_ui_for_current_mode();
            return False
        return True

    def _save_current_effects(self):
        if self.current_mode_index < len(self.wizard.analysis_data['effects']):
            self.wizard.analysis_data['effects'][self.current_mode_index] = [
                self.aircraft_effect_edit.toPlainText(), self.airspace_effect_edit.toPlainText(),
                self.gcs_effect_edit.toPlainText()]

    def update_ui_for_current_mode(self):
        modes = self.wizard.analysis_data['selected_modes']
        mode = modes[self.current_mode_index]
        self.setTitle(f"第二步：分析影响 ({self.current_mode_index + 1}/{len(modes)})")
        self.title_label.setText(f"<b>当前分析的失效模式: {mode}</b>")
        effects = self.wizard.analysis_data['effects'][self.current_mode_index]
        self.aircraft_effect_edit.setPlainText(effects[0]);
        self.airspace_effect_edit.setPlainText(effects[1]);
        self.gcs_effect_edit.setPlainText(effects[2])


class AssessHazardPage(BaseAnalysisPage):
    def __init__(self, wizard, parent=None):
        super().__init__(wizard, parent)
        self.hazard_categories = FHA_Model.ARP4761_CATEGORIES
        layout = QFormLayout(self)
        self.title_label, self.summary_label, self.hazard_combo, self.reason_edit = QLabel(), QTextEdit(), QComboBox(), QTextEdit()
        self.summary_label.setReadOnly(True);
        self.hazard_combo.addItems(self.hazard_categories)
        layout.addRow(self.title_label);
        layout.addRow("影响汇总(只读):", self.summary_label)
        layout.addRow("<b>最终危害性分类:</b>", self.hazard_combo);
        layout.addRow("理由/备注:", self.reason_edit)

    def initializePage(self):
        self.current_mode_index = 0
        self.wizard.analysis_data['hazards'] = [["", ""] for _ in self.wizard.analysis_data['selected_modes']]
        if self.wizard.analysis_data['selected_modes']: self.update_ui_for_current_mode()

    def validatePage(self):
        self._save_current_hazard()
        if self.current_mode_index < len(self.wizard.analysis_data['selected_modes']) - 1:
            self.current_mode_index += 1;
            self.update_ui_for_current_mode();
            return False
        self._assemble_final_results();
        return True

    def _save_current_hazard(self):
        if self.current_mode_index < len(self.wizard.analysis_data['hazards']):
            self.wizard.analysis_data['hazards'][self.current_mode_index] = [self.hazard_combo.currentText(),
                                                                             self.reason_edit.toPlainText()]

    def update_ui_for_current_mode(self):
        modes, effects = self.wizard.analysis_data['selected_modes'], self.wizard.analysis_data['effects']
        mode, effect_texts = modes[self.current_mode_index], effects[self.current_mode_index]
        self.setTitle(f"第三步：评估危害等级 ({self.current_mode_index + 1}/{len(modes)})")
        self.title_label.setText(f"<b>当前评估的失效模式: {mode}</b>")
        self.summary_label.setPlainText(
            f"对飞行器影响: {effect_texts[0]}\n对地面/空域影响: {effect_texts[1]}\n对地面控制组影响: {effect_texts[2]}")
        hazard = self.wizard.analysis_data['hazards'][self.current_mode_index]
        self.hazard_combo.setCurrentText(hazard[0]);
        self.reason_edit.setPlainText(hazard[1])

    def _assemble_final_results(self):
        self.wizard.final_results = []
        data = self.wizard.analysis_data
        for i, mode in enumerate(data.get('selected_modes', [])):
            self.wizard.final_results.append({
                '失效状态': mode, '对于飞行器的影响': data['effects'][i][0],
                '对于地面/空域的影响': data['effects'][i][1], '对于地面控制组的影响': data['effects'][i][2],
                '危害性分类': data['hazards'][i][0], '理由/备注': data['hazards'][i][1]})


# ------------------- 风险摘要仪表盘模块 (已重构) -------------------
class SummaryDashboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fha_model = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. 顶部KPIs
        kpi_layout = QHBoxLayout()
        font = QFont();
        font.setPointSize(16);
        font.setBold(True)

        self.total_label = QLabel("总条目数: 0");
        self.total_label.setFont(font)
        self.cat_label = QLabel("灾难级: 0");
        self.cat_label.setFont(font);
        self.cat_label.setStyleSheet("color: #D32F2F;")
        self.haz_label = QLabel("危险级: 0");
        self.haz_label.setFont(font);
        self.haz_label.setStyleSheet("color: #FFA000;")

        kpi_layout.addWidget(self.total_label);
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.cat_label);
        kpi_layout.addStretch()
        kpi_layout.addWidget(self.haz_label)

        # 2. 中部，左右分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 2.1 左侧图表
        self.fig = Figure(figsize=(8, 8), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # 2.2 右侧智能摘要与交叉矩阵
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.summary_text = QTextEdit();
        self.summary_text.setReadOnly(True)
        self.cross_analysis_table = QTableWidget();

        right_layout.addWidget(QLabel("<b>智能分析与建议</b>"))
        right_layout.addWidget(self.summary_text)
        right_layout.addWidget(QLabel("<b>风险/功能 交叉分析矩阵</b>"))
        right_layout.addWidget(self.cross_analysis_table)

        splitter.addWidget(self.canvas)
        splitter.addWidget(right_panel)
        splitter.setSizes([700, 450])

        main_layout.addLayout(kpi_layout)
        main_layout.addWidget(splitter)

    def set_model(self, model):
        self.fha_model = model

    def refresh_dashboard(self):
        if self.fha_model is None or self.fha_model.get_dataframe().empty:
            self._clear_dashboard();
            return

        df = self.fha_model.get_dataframe()
        self._update_kpis(df)
        self._update_sunburst_chart(df)
        self._update_cross_analysis(df)

    def _clear_dashboard(self):
        self.total_label.setText("总条目数: 0")
        self.cat_label.setText("灾难级: 0")
        self.haz_label.setText("危险级: 0")
        self.ax.clear();
        if self.fig.legends:
            self.fig.legends.clear()
        self.canvas.draw()
        self.summary_text.clear()
        self.cross_analysis_table.clear()
        self.cross_analysis_table.setRowCount(0)
        self.cross_analysis_table.setColumnCount(0)

    def _update_kpis(self, df):
        total_items = len(df[df['失效状态'] != ''])
        hazard_counts = df['危害性分类'].value_counts()
        cat_count = hazard_counts.get("灾难的 (Catastrophic)", 0)
        haz_count = hazard_counts.get("危险的 (Hazardous)", 0)

        self.total_label.setText(f"总条目数: {total_items}")
        self.cat_label.setText(f"灾难级: {cat_count}")
        self.haz_label.setText(f"危险级: {haz_count}")

    def _update_sunburst_chart(self, df):
        self.ax.clear()
        if self.fig.legends:
            self.fig.legends.clear()

        df_filtered = df[
            (df['一级功能'] != '') & (df['危害性分类'] != '') & (df['危害性分类'] != '无安全影响 (No Safety Effect)')]
        if df_filtered.empty:
            self.ax.text(0.5, 0.5, '无可用数据', ha='center', va='center', transform=self.ax.transAxes)
            self.ax.set_axis_off()
            self.canvas.draw()
            return

        # --- 数据准备 ---
        data = df_filtered.groupby(['一级功能', '危害性分类']).size().reset_index(name='size')
        func_sizes = data.groupby('一级功能')['size'].sum()
        hazard_counts = data.groupby('危害性分类')['size'].sum()

        color_map = {
            "灾难的 (Catastrophic)": "#D32F2F",
            "危险的 (Hazardous)": "#FFA000",
            "严重的 (Major)": "#388E3C",
            "轻微的 (Minor)": "#1976D2",
        }

        # --- 颜色优化：使用高对比度的颜色集tab20 ---
        func_colors = plt.cm.tab20(np.linspace(0, 1, len(func_sizes.index)))
        func_color_map = {func: color for func, color in zip(func_sizes.index, func_colors)}

        # --- 绘制旭日图 ---
        self.ax.set_aspect('equal')
        self.ax.set_axis_off()

        self.ax.pie(func_sizes, radius=0.6, colors=[func_color_map[f] for f in func_sizes.index],
                    wedgeprops=dict(width=0.3, edgecolor='w'))

        all_hazard_sizes = []
        all_hazard_colors = []
        for func_name in func_sizes.index:
            func_group = data[data['一级功能'] == func_name].set_index('危害性分类')
            for cat in color_map:
                if cat in func_group.index:
                    all_hazard_sizes.append(func_group.loc[cat, 'size'])
                    all_hazard_colors.append(color_map[cat])

        self.ax.pie(all_hazard_sizes, radius=0.9, colors=all_hazard_colors,
                    wedgeprops=dict(width=0.3, edgecolor='w'))

        # --- 将所有图例合并到右侧 ---
        all_patches = []
        func_patches = [mpatches.Patch(color=func_color_map[name], label=f"{name}: {size}")
                        for name, size in func_sizes.items()]
        all_patches.extend(func_patches)
        all_patches.append(mpatches.Patch(color='white', label=""))
        hazard_patches = [mpatches.Patch(color=color, label=f"{label.split(' ')[0]}: {hazard_counts.get(label, 0)}")
                          for label, color in color_map.items() if label in hazard_counts]
        all_patches.extend(hazard_patches)

        self.fig.legend(handles=all_patches, title="图例", loc='center right', bbox_to_anchor=(1.0, 0.5))

        self.ax.set_title("FHA 风险分布旭日图", pad=20)
        self.fig.tight_layout(rect=[0, 0, 0.8, 1])
        self.canvas.draw()

    def _update_cross_analysis(self, df):
        df_analyzed = df[(df['一级功能'] != '') & (df['危害性分类'] != '')].copy()
        if df_analyzed.empty:
            self.summary_text.setText("暂无已完成分析的条目。")
            self.cross_analysis_table.clear()
            self.cross_analysis_table.setRowCount(0)
            self.cross_analysis_table.setColumnCount(0)
            return

        # --- 生成交叉分析矩阵 ---
        cross_tab = pd.crosstab(df_analyzed['一级功能'], df_analyzed['危害性分类'])
        ordered_cols = [col for col in FHA_Model.ARP4761_CATEGORIES if col in cross_tab.columns and col != ""]
        cross_tab = cross_tab.reindex(columns=ordered_cols)

        # --- 填充QTableWidget ---
        self.cross_analysis_table.setRowCount(cross_tab.shape[0])
        self.cross_analysis_table.setColumnCount(cross_tab.shape[1])
        self.cross_analysis_table.setVerticalHeaderLabels(cross_tab.index)
        self.cross_analysis_table.setHorizontalHeaderLabels([col.split(' ')[0] for col in cross_tab.columns])

        for r, row_label in enumerate(cross_tab.index):
            for c, col_label in enumerate(cross_tab.columns):
                value = cross_tab.loc[row_label, col_label]
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if value > 0:
                    intensity = min(255, 50 + value * 40)
                    item.setBackground(QColor(255, 100, 100, intensity))
                self.cross_analysis_table.setItem(r, c, item)

        self.cross_analysis_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cross_analysis_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # --- 生成智能分析文本 ---
        text = ""
        high_risk_items = df_analyzed[df_analyzed['危害性分类'].isin(["灾难的 (Catastrophic)", "危险的 (Hazardous)"])]
        text += f"当前共识别出 {len(high_risk_items)} 项高风险条目（灾难级或危险级）。\n\n"

        if not cross_tab.empty:
            high_risk_cols = [col for col in ["灾难的 (Catastrophic)", "危险的 (Hazardous)"] if
                              col in cross_tab.columns]
            if high_risk_cols:
                top_func = cross_tab[high_risk_cols].sum(axis=1).idxmax()
                top_func_cat_count = cross_tab.loc[
                    top_func, "灾难的 (Catastrophic)"] if "灾难的 (Catastrophic)" in cross_tab.columns else 0
                top_func_haz_count = cross_tab.loc[
                    top_func, "危险的 (Hazardous)"] if "危险的 (Hazardous)" in cross_tab.columns else 0

                text += f"核心关注点：\n风险主要集中在 “{top_func}” 系统中，其中包含 {top_func_cat_count} 个“灾难级”和 {top_func_haz_count} 个“危险级”风险。\n\n"

        text += "行动建议：\n请结合下方交叉分析矩阵，优先审查红色高亮区域对应的功能模块，并为这些风险制定缓解措施和验证计划。"
        self.summary_text.setText(text)


# ------------------- 主窗口与应用入口 -------------------
class FHA_MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FHA 结构化分析系统");
        self.setGeometry(50, 50, 1600, 900)
        self.fha_model = FHA_Model()
        self.init_ui()
        self.update_all_views()

    def init_ui(self):
        self.tabs = QTabWidget();
        self.setCentralWidget(self.tabs)
        self.fha_table_tab = QWidget()
        table_layout = QVBoxLayout(self.fha_table_tab)
        self.table_view = QTableView();
        self.table_view.setAlternatingRowColors(True)
        table_layout.addWidget(self.table_view);
        self.tabs.addTab(self.fha_table_tab, "FHA 总表")

        self.dashboard_tab = SummaryDashboardWidget();
        self.tabs.addTab(self.dashboard_tab, "风险摘要")

        self.setup_delegates()
        self.create_actions();
        self.create_toolbar()
        self.setStatusBar(QStatusBar());
        self.statusBar().showMessage("准备就绪")
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def setup_delegates(self):
        hazard_delegate = ComboBoxDelegate(FHA_Model.ARP4761_CATEGORIES, self.table_view)
        try:
            hazard_col_index = FHA_Model.TABLE_COLUMNS.index('危害性分类')
            self.table_view.setItemDelegateForColumn(hazard_col_index, hazard_delegate)
        except ValueError:
            print("警告：无法找到'危害性分类'列，下拉框编辑功能将不可用。")

    def create_actions(self):
        self.new_action = QAction("&新建分析项目...", self, triggered=self.new_project)
        self.import_action = QAction("&导入旧格式表格...", self, triggered=self.import_legacy_file)
        self.export_action = QAction("&导出为表格...", self, triggered=self.export_to_file)
        self.analyze_action = QAction("&引导式分析...", self, triggered=self.start_analysis_wizard)
        self.add_row_action = QAction("&添加行", self, triggered=self.add_new_row)
        self.delete_row_action = QAction("&删除选中行", self, triggered=self.delete_selected_rows)

    def create_toolbar(self):
        toolbar = QToolBar("主工具栏");
        self.addToolBar(toolbar)
        toolbar.addAction(self.new_action);
        toolbar.addSeparator()
        toolbar.addAction(self.import_action);
        toolbar.addAction(self.export_action);
        toolbar.addSeparator()
        toolbar.addAction(self.add_row_action);
        toolbar.addAction(self.delete_row_action)
        toolbar.addSeparator();
        toolbar.addAction(self.analyze_action)

    def new_project(self):
        if not self.fha_model.get_dataframe().empty and QMessageBox.question(self, "确认",
                                                                             "这将清空所有当前数据，确定要新建项目吗？") == QMessageBox.StandardButton.No: return
        dialog = FunctionalArchitectDialog(self)
        if dialog.exec():
            self.fha_model.new_project();
            skeleton = dialog.get_fha_skeleton()
            self.fha_model.add_fha_entries(skeleton);
            self.update_all_views()
            self.statusBar().showMessage(f"项目框架已生成，包含 {len(skeleton)} 个待分析条目。")

    def import_legacy_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "选择Excel文件", "", "Excel Files (*.xlsx *.xls)")
        if filepath:
            df, msg = import_from_excel(filepath)
            if df is not None:
                self.fha_model.load_dataframe(df);
                self.update_all_views()
                self.statusBar().showMessage(f"成功从 {filepath.split('/')[-1]} 加载数据。")
            else:
                QMessageBox.critical(self, "错误", msg)

    def export_to_file(self):
        if self.fha_model.get_dataframe().empty: QMessageBox.warning(self, "警告", "没有可导出的数据。"); return
        filepath, _ = QFileDialog.getSaveFileName(self, "保存报告", "", "Excel Files (*.xlsx)")
        if filepath:
            success, msg = export_to_excel(self.fha_model.get_dataframe(), filepath)
            QMessageBox.information(self, "成功", msg) if success else QMessageBox.warning(self, "警告", msg)

    def add_new_row(self):
        self.fha_model.add_fha_entries([{}]);
        self.update_all_views()
        self.table_view.scrollToBottom();
        self.statusBar().showMessage("已在表格末尾添加一个新行。")

    def start_analysis_wizard(self):
        selected = self.table_view.selectionModel().selectedRows()
        if not selected: QMessageBox.warning(self, "警告", "请先在'FHA总表'中选择一个待分析的行。"); return
        source_index = selected[0].row()
        wizard = AnalysisWizard(self.fha_model.get_dataframe().iloc[source_index].to_dict(), self)

        if wizard.exec() == QDialog.DialogCode.Accepted:
            results = wizard.final_results
            if not results:
                QMessageBox.information(self, "提示", "分析已取消或未选择任何失效模式。")
                return
            self.fha_model.update_fha_entries_from_wizard(source_index, results)
            self.update_all_views();
            self.statusBar().showMessage("分析完成，表格已更新。")
        else:
            self.statusBar().showMessage("分析已取消。")

    def delete_selected_rows(self):
        selected = self.table_view.selectionModel().selectedRows()
        if not selected: QMessageBox.warning(self, "警告", "请先选择要删除的行。"); return
        if QMessageBox.question(self, "确认删除",
                                f"确定要删除选中的 {len(selected)} 行吗？") == QMessageBox.StandardButton.Yes:
            indices_to_delete = sorted([index.row() for index in selected], reverse=True)
            self.fha_model.delete_rows(indices_to_delete)
            self.update_all_views();
            self.statusBar().showMessage(f"已删除 {len(indices_to_delete)} 行。")

    def on_tab_changed(self, index):
        if self.tabs.widget(index) == self.dashboard_tab:
            self.dashboard_tab.refresh_dashboard()
            self.statusBar().showMessage("风险摘要仪表盘已刷新。")
        else:
            self.statusBar().showMessage("切换到FHA总表视图。")

    def update_all_views(self):
        pandas_model = PandasModel(self.fha_model.get_dataframe())
        self.table_view.setModel(pandas_model)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.dashboard_tab.set_model(self.fha_model)
        if self.tabs.currentWidget() == self.dashboard_tab:
            self.dashboard_tab.refresh_dashboard()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_win = FHA_MainWindow()
    main_win.show()
    sys.exit(app.exec())
