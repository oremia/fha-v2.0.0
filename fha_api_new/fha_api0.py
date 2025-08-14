from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import pandas as pd
import io
import uuid
from datetime import datetime

# 导入核心业务逻辑
from fha_core_logic import FHA_Model, FAILURE_MODE_LIBRARY

app = FastAPI(title="FHA 结构化分析系统 API",
              description="提供FHA分析系统的后端API接口",
              version="1.0.0")

# 存储项目会话的内存数据库
projects_db = {}


# Pydantic 模型定义
class ProjectCreate(BaseModel):
    name: str = Field(..., example="无人机飞控系统FHA分析", description="项目名称")


class ProjectResponse(BaseModel):
    project_id: str = Field(..., description="项目唯一标识符")
    name: str = Field(..., example="无人机飞控系统FHA分析", description="项目名称")
    created_at: datetime = Field(..., description="项目创建时间")


class FHAEntry(BaseModel):
    编号: Optional[str] = ""
    一级功能: Optional[str] = ""
    二级功能: Optional[str] = ""
    三级功能: Optional[str] = ""
    功能类型: Optional[str] = ""
    飞行阶段: Optional[str] = ""
    失效状态: Optional[str] = ""
    对于飞行器的影响: Optional[str] = ""
    对于地面或空域的影响: Optional[str] = Field("", alias="对于地面/空域的影响")
    对于地面控制组的影响: Optional[str] = ""
    危害性分类: Optional[str] = ""
    理由或备注: Optional[str] = Field("", alias="理由/备注")

    class Config:
        allow_population_by_field_name = True

class FHAEntryUpdate(BaseModel):
    一级功能: Optional[str] = None
    二级功能: Optional[str] = None
    三级功能: Optional[str] = None
    功能类型: Optional[str] = None
    飞行阶段: Optional[str] = None
    失效状态: Optional[str] = None
    对于飞行器的影响: Optional[str] = None
    对于地面或空域的影响: Optional[str] = Field(None, alias="对于地面/空域的影响")
    对于地面控制组的影响: Optional[str] = None
    危害性分类: Optional[str] = None
    理由或备注: Optional[str] = Field("", alias="理由/备注")
    class Config:
        allow_population_by_field_name = True

class WizardResult(BaseModel):
    """定义“引导式分析”结果中，单个分析条目的数据结构。"""
    失效状态: str = Field(..., example="功能完全丧失")
    对于飞行器的影响: str = Field(..., example="无法接收GPS信号，失去精确定位能力。")
    对于地面或空域的影响: str = Field(..., alias='对于地面/空域的影响', example="无直接影响。")
    对于地面控制组的影响: str = Field(..., example="地面站显示位置信息丢失告警。")
    危害性分类: str = Field(..., example="危险的 (Hazardous)")
    理由或备注: str = Field(..., alias='理由/备注', example="在复杂空域下可能导致飞行冲突。")

class WizardAnalysisRequest(BaseModel):
    """定义"引导式分析"接口的请求体结构。"""
    source_index: int = Field(..., description="要被替换的原始行的位置索引。", example=5)
    results: List[WizardResult] = Field(..., description="分析结果列表")

class FunctionalArchitectData(BaseModel):
    skeleton: List[Dict[str, str]] = Field(..., description="功能架构骨架数据")


# 依赖项 - 获取项目模型
def get_project_model(project_id: str) -> FHA_Model:
    """获取指定项目的FHA模型实例"""
    if project_id not in projects_db:
        raise HTTPException(status_code=404, detail="Project not found")
    return projects_db[project_id]["model"]


# API 路由
@app.get("/", tags=["系统信息"],
         summary="API根路径",
         description="返回API系统基本信息，用于健康检查和确认服务状态")
async def root():
    """API根路径"""
    return {"message": "FHA 结构化分析系统 API"}


# 项目管理 API
@app.post("/projects", response_model=ProjectResponse, tags=["项目管理"],
          summary="创建新项目",
          description="创建一个新的FHA分析项目，返回项目ID和其他基本信息")
async def create_project(project: ProjectCreate):
    """创建新项目"""
    project_id = str(uuid.uuid4())
    model = FHA_Model()
    projects_db[project_id] = {
        "name": project.name,
        "model": model,
        "created_at": datetime.now()
    }

    return ProjectResponse(
        project_id=project_id,
        name=project.name,
        created_at=projects_db[project_id]["created_at"]
    )


@app.get("/projects", tags=["项目管理"],
         summary="列出所有项目",
         description="获取系统中所有FHA项目的列表，包括项目ID、名称、创建时间和条目数量")
async def list_projects():
    """列出所有项目"""
    return [
        {
            "project_id": pid,
            "name": proj["name"],
            "created_at": proj["created_at"],
            "entry_count": len(proj["model"].get_dataframe())
        }
        for pid, proj in projects_db.items()
    ]


@app.delete("/projects/{project_id}", tags=["项目管理"],
            summary="删除项目",
            description="根据项目ID删除指定的FHA项目及其所有相关数据")
async def delete_project(project_id: str):
    """删除项目"""
    if project_id not in projects_db:
        raise HTTPException(status_code=404, detail="Project not found")

    del projects_db[project_id]
    return {"message": "Project deleted successfully"}


@app.post("/projects/{project_id}/new", tags=["项目管理"],
          summary="创建空白项目",
          description="清空指定项目的数据，创建一个新的空白项目")
async def new_project(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """清空项目数据，创建新的空白项目"""
    model.new_project()
    return {"message": "New project created"}


# 数据管理 API
@app.get("/projects/{project_id}/entries", response_model=List[FHAEntry], tags=["数据管理"],
         summary="获取项目所有条目",
         description="获取指定项目中的所有FHA分析条目数据")
async def get_entries(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """获取所有FHA条目"""
    df = model.get_dataframe()
    entries = []
    for _, row in df.iterrows():
        entries.append(FHAEntry.parse_obj(row.to_dict()))
    return entries


@app.post("/projects/{project_id}/entries", tags=["数据管理"],
          summary="添加新条目",
          description="向指定项目中添加一个新的FHA分析条目")
async def add_entry(project_id: str, entry: FHAEntry, model: FHA_Model = Depends(get_project_model)):
    """添加新的FHA条目"""
    entry_dict = entry.dict()
    model.add_fha_entries([entry_dict])
    return {"message": "Entry added successfully"}


@app.put("/projects/{project_id}/entries/{entry_index}", tags=["数据管理"],
         summary="更新指定条目",
         description="更新指定项目中指定索引位置的FHA分析条目")
async def update_entry(project_id: str, entry_index: int, entry: FHAEntryUpdate,
                       model: FHA_Model = Depends(get_project_model)):
    """更新指定的FHA条目"""
    df = model.get_dataframe()
    if entry_index >= len(df):
        raise HTTPException(status_code=404, detail="Entry not found")

    # 更新指定行的数据
    update_data = {k: v for k, v in entry.dict().items() if v is not None}
    for key, value in update_data.items():
        df.loc[entry_index, key] = value

    return {"message": "Entry updated successfully"}


@app.delete("/projects/{project_id}/entries/{entry_indices}", tags=["数据管理"],
            summary="删除指定条目",
            description="删除指定项目中指定索引位置的一个或多个FHA分析条目")
async def delete_entries(project_id: str, entry_indices: str,
                         model: FHA_Model = Depends(get_project_model)):
    """删除指定的FHA条目"""
    try:
        indices = [int(i) for i in entry_indices.split(",")]
        model.delete_rows(indices)
        return {"message": f"Entries {indices} deleted successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry indices format")


# 功能架构 API
@app.post("/projects/{project_id}/functional-architect", tags=["功能架构"],
          summary="创建功能架构",
          description="根据功能架构向导数据创建FHA条目框架")
async def create_from_functional_architect(project_id: str, data: FunctionalArchitectData,
                                           model: FHA_Model = Depends(get_project_model)):
    """根据功能架构向导数据创建FHA条目"""
    model.new_project()
    skeleton = data.skeleton
    model.add_fha_entries(skeleton)
    return {"message": f"Project framework generated with {len(skeleton)} entries"}


# 引导式分析向导 API
@app.get("/projects/{project_id}/failure-modes/{function_type}", tags=["分析向导"],
         summary="获取指定功能类型的失效模式",
         description="根据功能类型获取相应的失效模式列表，用于引导式分析向导的第一步。可选功能类型: 电源, 传感器, 执行机构, 数据传输, 飞控算法, 导航, 通信, 其他")
async def get_failure_modes(function_type: str):
    """获取指定功能类型的失效模式"""
    modes = list(set(FAILURE_MODE_LIBRARY.get("通用", []) +
                     FAILURE_MODE_LIBRARY.get(function_type, [])))
    return {"failure_modes": sorted(modes)}


@app.post("/projects/{project_id}/analysis-wizard", tags=["分析向导"],
          summary="运行引导式分析向导",
          description="基于选择的失效模式进行详细分析，生成完整的FHA条目信息")
async def run_analysis_wizard(
        project_id: str,
        data: WizardAnalysisRequest,
        model: FHA_Model = Depends(get_project_model)
):
    """运行引导式分析向导"""
    # 验证项目是否存在
    if project_id not in projects_db:
        raise HTTPException(status_code=404, detail="Project not found")

    df = model.get_dataframe()
    if data.source_index >= len(df):
        raise HTTPException(status_code=404, detail="Entry not found")

    # 组装最终结果
    final_results = []
    for result in data.results:
        final_results.append({
            '失效状态': result.失效状态,
            '对于飞行器的影响': result.对于飞行器的影响,
            '对于地面/空域的影响': result.对于地面空域的影响,
            '对于地面控制组的影响': result.对于地面控制组的影响,
            '危害性分类': result.危害性分类,
            '理由/备注': result.理由备注
        })

    # 更新模型数据
    model.update_fha_entries_from_wizard(data.source_index, final_results)

    return {"message": "Analysis completed", "results": final_results}


# 仪表盘数据 API
@app.get("/projects/{project_id}/dashboard/kpis", tags=["仪表盘"],
         summary="获取仪表盘KPI数据",
         description="获取项目的关键绩效指标数据，包括总条目数、灾难级和危险级条目数")
async def get_dashboard_kpis(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """获取仪表盘KPI数据"""
    df = model.get_dataframe()
    total_items = len(df[df['失效状态'] != ''])
    hazard_counts = df['危害性分类'].value_counts()
    cat_count = int(hazard_counts.get("灾难的 (Catastrophic)", 0))
    haz_count = int(hazard_counts.get("危险的 (Hazardous)", 0))

    return {
        "total_items": total_items,
        "catastrophic_count": cat_count,
        "hazardous_count": haz_count
    }


@app.get("/projects/{project_id}/dashboard/sunburst-data", tags=["仪表盘"],
         summary="获取旭日图数据",
         description="获取用于生成风险分布旭日图的数据")
async def get_sunburst_data(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """获取旭日图数据"""
    df = model.get_dataframe()
    df_filtered = df[
        (df['一级功能'] != '') & (df['危害性分类'] != '') & (df['危害性分类'] != '无安全影响 (No Safety Effect)')
        ]

    if df_filtered.empty:
        return {"data": []}

    # 数据准备
    data = df_filtered.groupby(['一级功能', '危害性分类']).size().reset_index(name='size')
    func_sizes = data.groupby('一级功能')['size'].sum()

    result = []
    for func_name in func_sizes.index:
        func_data = {"function": func_name, "total": int(func_sizes[func_name]), "categories": []}
        func_group = data[data['一级功能'] == func_name].set_index('危害性分类')
        for cat in ["灾难的 (Catastrophic)", "危险的 (Hazardous)", "严重的 (Major)", "轻微的 (Minor)"]:
            if cat in func_group.index:
                func_data["categories"].append({
                    "category": cat,
                    "count": int(func_group.loc[cat, 'size'])
                })
        result.append(func_data)

    return {"data": result}


@app.get("/projects/{project_id}/dashboard/cross-analysis", tags=["仪表盘"],
         summary="获取交叉分析矩阵数据",
         description="获取风险/功能交叉分析矩阵数据，用于识别高风险功能模块")
async def get_cross_analysis_data(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """获取交叉分析矩阵数据"""
    df = model.get_dataframe()
    df_analyzed = df[(df['一级功能'] != '') & (df['危害性分类'] != '')].copy()

    if df_analyzed.empty:
        return {"matrix": [], "summary": "暂无已完成分析的条目。"}

    # 生成交叉分析矩阵
    cross_tab = pd.crosstab(df_analyzed['一级功能'], df_analyzed['危害性分类'])
    ordered_cols = [col for col in FHA_Model.ARP4761_CATEGORIES if col in cross_tab.columns and col != ""]
    cross_tab = cross_tab.reindex(columns=ordered_cols)

    # 转换为JSON格式
    matrix_data = []
    for func in cross_tab.index:
        row_data = {"function": func}
        for col in cross_tab.columns:
            row_data[col.split(' ')[0] if col else ""] = int(cross_tab.loc[func, col])
        matrix_data.append(row_data)

    # 生成摘要文本
    high_risk_items = df_analyzed[df_analyzed['危害性分类'].isin(["灾难的 (Catastrophic)", "危险的 (Hazardous)"])]
    summary = f"当前共识别出 {len(high_risk_items)} 项高风险条目（灾难级或危险级）。"

    if not cross_tab.empty:
        high_risk_cols = [col for col in ["灾难的 (Catastrophic)", "危险的 (Hazardous)"] if col in cross_tab.columns]
        if high_risk_cols:
            top_func = cross_tab[high_risk_cols].sum(axis=1).idxmax()
            top_func_cat_count = cross_tab.loc[
                top_func, "灾难的 (Catastrophic)"] if "灾难的 (Catastrophic)" in cross_tab.columns else 0
            top_func_haz_count = cross_tab.loc[
                top_func, "危险的 (Hazardous)"] if "危险的 (Hazardous)" in cross_tab.columns else 0

            summary += f"\n风险主要集中在 \"{top_func}\" 系统中，其中包含 {int(top_func_cat_count)} 个\"灾难级\"和 {int(top_func_haz_count)} 个\"危险级\"风险。"

    return {
        "matrix": matrix_data,
        "summary": summary
    }


# 文件导入/导出 API
@app.post("/projects/{project_id}/import", tags=["文件操作"],
          summary="导入Excel文件",
          description="从Excel文件导入FHA数据到指定项目中")
async def import_excel(project_id: str, file: UploadFile = File(...),
                       model: FHA_Model = Depends(get_project_model)):
    """从Excel文件导入数据"""
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents), engine='openpyxl')
        model.load_dataframe(df)
        return {"message": f"Successfully imported data from {file.filename}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to import file: {str(e)}")


@app.get("/projects/{project_id}/export", tags=["文件操作"],
         summary="导出为Excel文件",
         description="将指定项目中的FHA数据导出为Excel文件")
async def export_excel(project_id: str, model: FHA_Model = Depends(get_project_model)):
    """导出数据为Excel格式"""
    df = model.get_dataframe()
    if df.empty:
        raise HTTPException(status_code=400, detail="No data to export")

    # 将DataFrame转换为字节流
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)

    # 返回字节流作为响应
    headers = {
        'Content-Disposition': 'attachment; filename="fha_export.xlsx"'
    }
    return Response(content=output.read(), headers=headers,
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# 错误处理
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """全局异常处理器"""
    return JSONResponse(
        status_code=500,
        content={"message": f"An error occurred: {str(exc)}"},
    )


# 为API文档添加额外信息
@app.get("/config/failure-mode-library", tags=["配置信息"],
         summary="获取失效模式知识库",
         description="获取系统内置的失效模式知识库，包含各种功能类型的典型失效模式")
async def get_failure_mode_library():
    """获取失效模式知识库"""
    return FAILURE_MODE_LIBRARY

@app.get("/config/arp4761-categories", tags=["配置信息"],
         summary="获取ARP4761危害性分类",
         description="获取ARP4761标准定义的危害性分类列表")
async def get_arp4761_categories():
    """获取ARP4761危害性分类"""
    return {"categories": FHA_Model.ARP4761_CATEGORIES}

@app.get("/config/table-columns", tags=["配置信息"],
         summary="获取表格列定义",
         description="获取FHA分析表格的列定义信息")
async def get_table_columns():
    """获取表格列定义"""
    return {"columns": FHA_Model.TABLE_COLUMNS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
