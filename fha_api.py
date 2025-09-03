# fha_api.py
"""
功能危险性分析 (Functional Hazard Analysis, FHA) API 模块(源于fastAPI v1.0.0)

本模块负责处理所有与FHA相关的数据操作和业务逻辑。
它提供了一个完整的CRUD（创建、读取、更新、删除）功能的API，用于管理FHA表格数据。
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import pandas as pd
import io

# ==============================================================================
# 模块路由设置
# ==============================================================================
router = APIRouter()


# ==============================================================================
# 核心数据模型与业务逻辑 (Core Data Model & Business Logic)
# ==============================================================================
class FHA_Model:
    """
    FHA功能的数据核心，封装了所有基于Pandas DataFrame的数据操作。
    """
    TABLE_COLUMNS = [
        '编号', '一级功能', '二级功能', '三级功能', '功能类型', '飞行阶段',
        '失效状态', '对于飞行器的影响', '对于地面/空域的影响', '对于地面控制组的影响',
        '危害性分类', '理由/备注',
    ]
    ARP4761_CATEGORIES = [
        "", "灾难的 (Catastrophic)", "危险的 (Hazardous)", "严重的 (Major)",
        "轻微的 (Minor)", "无安全影响 (No Safety Effect)"
    ]

    def __init__(self):
        self.dataframe = pd.DataFrame(columns=self.TABLE_COLUMNS)

    def load_dataframe(self, df: pd.DataFrame):
        df_reset = df.reset_index(drop=True)
        self.dataframe = df_reset.reindex(columns=self.TABLE_COLUMNS).fillna('')
        self.re_number_ids()

    def update_cell(self, row_index: int, column_name: str, new_value: Any):
        if row_index >= len(self.dataframe) or column_name not in self.dataframe.columns:
            raise IndexError("行或列的索引/名称超出了范围。")
        self.dataframe.loc[row_index, column_name] = new_value

    def delete_rows(self, row_indices: List[int]):
        if not row_indices or self.dataframe.empty: return
        positions_to_delete = set(row_indices)
        rows_to_keep = [row for index, row in self.dataframe.iterrows() if index not in positions_to_delete]
        if not rows_to_keep:
            self.dataframe = pd.DataFrame(columns=self.TABLE_COLUMNS)
        else:
            self.dataframe = pd.DataFrame(rows_to_keep).reset_index(drop=True)
        self.re_number_ids()

    def add_fha_entries(self, entries_list: List[Dict]):
        if not entries_list: return
        new_df = pd.DataFrame(entries_list, columns=self.TABLE_COLUMNS).fillna('')
        self.dataframe = pd.concat([self.dataframe, new_df], ignore_index=True)
        self.re_number_ids()

    def update_fha_entries_from_wizard(self, source_index: int, wizard_results: List[Dict]):
        if not wizard_results: return
        df_before = self.dataframe.iloc[:source_index]
        df_after = self.dataframe.iloc[source_index + 1:]
        new_entries = []
        source_row_data = self.dataframe.loc[source_index].copy()
        for result in wizard_results:
            new_entry = source_row_data.copy()
            new_entry.update(result)
            new_entries.append(new_entry)
        df_new = pd.DataFrame(new_entries, columns=self.TABLE_COLUMNS)
        self.dataframe = pd.concat([df_before, df_new, df_after], ignore_index=True)
        self.re_number_ids()

    def re_number_ids(self):
        if self.dataframe.empty: return
        for i in range(len(self.dataframe)):
            self.dataframe.loc[i, '编号'] = f"FHA-{i + 1:03d}"


# --- 模块内的常量定义 ---
FAILURE_MODE_LIBRARY = {"通用": ["功能完全丧失", "功能间歇性工作", "功能性能下降", "功能非预期启动"],
                        "传感器": ["持续输出错误信息", "输出数据冻结/卡死", "数据跳变/噪声过大", "输出数据延迟"],
                        "数据传输": ["数据包丢失", "数据完整性破坏 (误码)", "通信中断"],
                        "执行机构": ["无响应/卡死", "响应延迟/迟钝", "动作超调/不到位", "反向运动"],
                        "电源": ["电压/电流异常", "供电中断"], "导航": ["定位精度下降", "航向错误", "速度信息错误"],
                        "飞控算法": ["算法发散", "模式切换错误"]}
MISSION_PHASES = ["地面检查", "启动", "垂直起飞", "过渡飞行", "巡航", "悬停作业", "返航", "垂直降落", "关机"]
FUNCTION_TYPES = ["电源", "传感器", "执行机构", "数据传输", "飞控算法", "导航", "通信", "其他"]

fha_model_instance = FHA_Model()


# ==============================================================================
# API 数据模型 (Pydantic Models)
# ==============================================================================
class FHAEntry(BaseModel):
    """定义“新建项目”时，单个功能骨架条目的数据结构。"""
    一级功能: str = Field("", example="导航系统")
    二级功能: str = Field("", example="GPS接收机")
    三级功能: str = Field("", example="")
    功能类型: str = Field("", example="导航")
    飞行阶段: str = Field("", example="巡航")


class CellUpdateRequest(BaseModel):
    """定义“更新单元格”接口的请求体结构。"""
    row_index: int = Field(..., description="要更新的行的位置索引（从0开始）。", example=0)
    column_name: str = Field(..., description="要更新的列的名称。", example="理由/备注")
    new_value: Any = Field(..., description="单元格的新值。", example="根据最新测试数据更新。")


class WizardResult(BaseModel):
    """定义“引导式分析”结果中，单个分析条目的数据结构。"""
    失效状态: str = Field(..., example="功能完全丧失")
    对于飞行器的影响: str = Field(..., example="无法接收GPS信号，失去精确定位能力。")
    对于地面空域的影响: str = Field(..., alias='对于地面/空域的影响', example="无直接影响。")
    对于地面控制组的影响: str = Field(..., example="地面站显示位置信息丢失告警。")
    危害性分类: str = Field(..., example="危险的 (Hazardous)")
    理由备注: str = Field(..., alias='理由/备注', example="在复杂空域下可能导致飞行冲突。")


class WizardAnalysisRequest(BaseModel):
    """定义“引导式分析”接口的请求体结构。"""
    source_index: int = Field(..., description="要被替换的原始行的位置索引。", example=5)
    results: List[WizardResult]


# ==============================================================================
# API 接口 (Endpoints)
# ==============================================================================
@router.post(
    "/fha/project/new",
    summary="新建一个FHA项目",
    description="清空当前所有数据，并根据提供的功能骨架列表创建一个全新的FHA项目。"
)
def new_project(entries: List[FHAEntry]):
    fha_model_instance.dataframe = pd.DataFrame(columns=FHA_Model.TABLE_COLUMNS)
    fha_model_instance.add_fha_entries([e.dict() for e in entries])
    return {"message": "项目框架已成功生成", "total": len(fha_model_instance.dataframe)}


@router.post(
    "/fha/import",
    summary="导入FHA表格",
    description="""
    通过上传一个完整的Excel(.xlsx)文件来加载FHA项目。此操作会覆盖所有当前数据。
    Excel格式要求:
    - 必须是一个标准的 `.xlsx` 文件。
    - 文件的第一行必须是表头。
    - 表头应尽可能与FHA表格的列名匹配，系统会自动匹配存在的列。
    """
)
async def import_fha_table(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="文件格式错误，请上传一个标准的 .xlsx Excel 文件。")
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents), engine='openpyxl').fillna('').astype(str)
        fha_model_instance.load_dataframe(df)
        return {"message": "FHA表格导入成功", "total": len(fha_model_instance.dataframe)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件处理失败: {e}")


@router.get(
    "/fha/export",
    summary="导出FHA表格为Excel",
    description="将当前项目中的所有FHA数据导出为一个标准的Excel(.xlsx)文件。"
)
def export_excel():
    if fha_model_instance.dataframe.empty:
        raise HTTPException(status_code=404, detail="没有可导出的数据。")
    output = io.BytesIO()
    fha_model_instance.dataframe.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fha_report.xlsx"}
    )


@router.get(
    "/fha/data",
    summary="获取FHA表格数据 (支持筛选)",
    description="""
    获取当前项目中的所有FHA数据行。
    高级功能：服务器端筛选
    - `hazard_category`: 按“危害性分类”进行精确匹配筛选。
    - `function_name`: 在“一级功能”、“二级功能”和“三级功能”三列中进行不区分大小写的模糊搜索。
    """
)
def get_fha_data(
        hazard_category: Optional[str] = Query(None, description="按危害性分类进行精确筛选。",
                                               example="危险的 (Hazardous)"),
        function_name: Optional[str] = Query(None, description="按功能名称进行模糊搜索。", example="导航")
) -> List[Dict[str, Any]]:
    df = fha_model_instance.dataframe.copy()
    if hazard_category:
        df = df[df['危害性分类'] == hazard_category]
    if function_name:
        df = df[df['一级功能'].str.contains(function_name, case=False, na=False) |
                df['二级功能'].str.contains(function_name, case=False, na=False) |
                df['三级功能'].str.contains(function_name, case=False, na=False)]
    return df.to_dict(orient='records')


@router.patch(
    "/fha/cell/update",
    summary="更新单个单元格数据",
    description="用于实现在表格内直接编辑的功能。此接口根据行、列位置精确更新一个单元格的值。"
)
def update_cell(request: CellUpdateRequest):
    try:
        fha_model_instance.update_cell(
            row_index=request.row_index,
            column_name=request.column_name,
            new_value=request.new_value
        )
        updated_row = fha_model_instance.dataframe.iloc[request.row_index].to_dict()
        return {"message": "更新成功", "updated_row": updated_row}
    except IndexError:
        raise HTTPException(status_code=404, detail="行或列不存在。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete(
    "/fha/rows/delete",
    summary="删除一个或多个FHA数据行",
    description="根据行的位置索引，从FHA表格中删除一行或多行。"
)
def delete_rows(indices: List[int] = Query(..., description="要删除的行的位置索引列表（从0开始）。")):
    try:
        fha_model_instance.delete_rows(indices)
        return {"message": f"已成功删除 {len(indices)} 行。", "new_total": len(fha_model_instance.dataframe)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除行时发生错误: {str(e)}")


@router.post(
    "/fha/wizard/analyze",
    summary="提交引导式分析结果",
    description="接收来自前端引导式分析向导的结果，用生成的多条新行替换掉原有的单条行。"
)
def wizard_analyze(request: WizardAnalysisRequest):
    try:
        results_dict = [r.dict(by_alias=True) for r in request.results]
        fha_model_instance.update_fha_entries_from_wizard(request.source_index, results_dict)
        return {"message": "分析完成，表格已更新。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理分析结果时出错: {e}")


@router.get(
    "/fha/dashboard",
    summary="获取仪表盘数据",
    description="计算并返回用于渲染前端“风险摘要”仪表盘的所有数据，包括KPIs、交叉分析矩阵和旭日图数据。"
)
def get_dashboard_data():
    df = fha_model_instance.dataframe
    if df.empty:
        return {"message": "无数据可供分析"}

    total_items = len(df[df['失效状态'] != ''])
    hazard_counts = df['危害性分类'].value_counts()
    cat_count = int(hazard_counts.get("灾难的 (Catastrophic)", 0))
    haz_count = int(hazard_counts.get("危险的 (Hazardous)", 0))
    kpis = {"total_items": total_items, "catastrophic_count": cat_count, "hazardous_count": haz_count}
    df_analyzed = df[(df['一级功能'] != '') & (df['危害性分类'] != '')].copy()
    cross_tab_data, summary_text = {}, "暂无已完成分析的条目。"
    if not df_analyzed.empty:
        cross_tab = pd.crosstab(df_analyzed['一级功能'], df_analyzed['危害性分类'])
        ordered_cols = [col for col in FHA_Model.ARP4761_CATEGORIES if col in cross_tab.columns and col != ""]
        cross_tab = cross_tab.reindex(columns=ordered_cols).fillna(0)
        cross_tab_data = {"index": cross_tab.index.tolist(), "columns": [c.split(' ')[0] for c in cross_tab.columns],
                          "data": cross_tab.values.tolist()}
        high_risk_items = df_analyzed[df_analyzed['危害性分类'].isin(["灾难的 (Catastrophic)", "危险的 (Hazardous)"])]
        summary_text = f"当前共识别出 {len(high_risk_items)} 项高风险条目（灾难级或危险级）。\n\n"
        if not cross_tab.empty:
            high_risk_cols = [col for col in ["灾难的 (Catastrophic)", "危险的 (Hazardous)"] if
                              col in cross_tab.columns]
            if high_risk_cols:
                top_func = cross_tab[high_risk_cols].sum(axis=1).idxmax()
                top_func_cat_count = int(cross_tab.loc[
                                             top_func, "灾难的 (Catastrophic)"]) if "灾难的 (Catastrophic)" in cross_tab.columns else 0
                top_func_haz_count = int(
                    cross_tab.loc[top_func, "危险的 (Hazardous)"]) if "危险的 (Hazardous)" in cross_tab.columns else 0
                summary_text += f"核心关注点：\n风险主要集中在 “{top_func}” 系统中，其中包含 {top_func_cat_count} 个“灾难级”和 {top_func_haz_count} 个“危险级”风险。\n\n"
        summary_text += "行动建议：\n请结合下方交叉分析矩阵，优先审查高风险区域对应的功能模块，并为这些风险制定缓解措施和验证计划。"
    sunburst_data = {}
    df_filtered = df[
        (df['一级功能'] != '') & (df['危害性分类'] != '') & (df['危害性分类'] != '无安全影响 (No Safety Effect)')]
    if not df_filtered.empty:
        data = df_filtered.groupby(['一级功能', '危害性分类']).size().reset_index(name='size')
        sunburst_data = {"name": "风险分布", "children": []}
        for func_name, func_group in data.groupby('一级功能'):
            func_node = {"name": func_name, "children": []}
            for _, row in func_group.iterrows():
                func_node["children"].append({"name": row['危害性分类'], "value": row['size']})
            sunburst_data["children"].append(func_node)

    return {"kpis": kpis, "cross_analysis": {"matrix": cross_tab_data, "summary_text": summary_text},
            "sunburst_data": sunburst_data}


@router.get(
    "/fha/definitions",
    summary="获取FHA相关定义",
    description="为前端提供渲染下拉菜单和选项列表所需的预定义数据。"
)
def get_definitions():
    return {
        "failure_modes": FAILURE_MODE_LIBRARY,
        "hazard_categories": FHA_Model.ARP4761_CATEGORIES,
        "function_types": FUNCTION_TYPES,
        "mission_phases": MISSION_PHASES,

    }
