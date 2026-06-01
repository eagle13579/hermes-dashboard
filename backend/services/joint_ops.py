"""
Hermes Dashboard — 联合作战模式 (Joint Operations) Service.

允许多个 Profile 编排成一个流水线，按顺序或并行执行协作任务。
每个 Stage 通过 subprocess 调用 ``hermes -p <profile> chat -q "<goal>"``
捕获输出，自动将上一步的上下文传递给下一步。

预定义模板
===========
- 代码评审流水线: chainke-dev 写代码 → gaia-city 架构评审 → zhairu 写文档
- 全栈开发: chainke-dev 后端 → dev 前端 → zhairu 写文档
- 产品上线检查: 多个 Profile 并行做健康检查
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

HERMES_HOME = Path.home() / "向海容的知识库" / "wiki" / "wiki" / "记忆宫殿"
DATA_DIR = HERMES_HOME / "profiles" / "hermes-dashboard" / "data"
DATA_FILE = DATA_DIR / "joint_ops.json"
TEMPLATES_FILE = DATA_DIR / "joint_templates.json"

# ── Data Models ────────────────────────────────────────────────────────


@dataclass
class JointStage:
    """联合作战中的单个 Stage。"""

    stage_id: str
    profile_name: str
    goal: str
    context_input: str = ""
    context_output: str = ""
    status: str = "pending"  # pending / running / completed / failed / cancelled
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> JointStage:
        return cls(**data)


@dataclass
class JointOperation:
    """一次联合作战任务的完整数据。"""

    op_id: str
    name: str
    description: str = ""
    status: str = "planning"  # planning / running / completed / failed / cancelled
    stages: list[JointStage] = field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None
    result_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "op_id": self.op_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "stages": [s.to_dict() for s in self.stages],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "result_summary": self.result_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> JointOperation:
        stages = [JointStage.from_dict(s) for s in data.get("stages", [])]
        return cls(
            op_id=data["op_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=data.get("status", "planning"),
            stages=stages,
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at"),
            result_summary=data.get("result_summary", ""),
        )


@dataclass
class JointTemplate:
    """预定义的联合作战模板。"""

    template_id: str
    name: str
    description: str
    stages: list[dict]  # list of {"profile_name": ..., "goal": ...}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> JointTemplate:
        return cls(**data)


# ── Predefined Templates ──────────────────────────────────────────────

_PREDEFINED_TEMPLATES: list[JointTemplate] = [
    JointTemplate(
        template_id="code-review-pipeline",
        name="代码评审流水线",
        description=(
            "代码开发 → 架构评审 → 文档撰写。chainke-dev 编写代码，"
            "gaia-city 做架构评审，zhairu 输出技术文档。"
        ),
        stages=[
            {
                "profile_name": "chainke-dev",
                "goal": "实现一个用户注册功能的完整代码，包含输入验证、数据库操作和错误处理",
            },
            {
                "profile_name": "gaia-city",
                "goal": "对上述代码进行架构评审，检查安全性、可扩展性和最佳实践",
            },
            {
                "profile_name": "zhairu",
                "goal": "根据上述代码和评审意见撰写完整的技术文档和使用说明",
            },
        ],
    ),
    JointTemplate(
        template_id="fullstack-dev",
        name="全栈开发",
        description=(
            "全栈应用开发流程：chainke-dev 完成后端 API 开发，dev 完成前端界面开发，"
            "zhairu 输出项目文档。"
        ),
        stages=[
            {
                "profile_name": "chainke-dev",
                "goal": "开发一个用户管理系统的后端 RESTful API，包括 CRUD 操作和 JWT 认证",
            },
            {
                "profile_name": "dev",
                "goal": "开发一个用户管理系统的前端界面，包括登录页面和用户列表页面",
            },
            {
                "profile_name": "zhairu",
                "goal": "撰写完整的全栈项目部署文档和 API 使用说明",
            },
        ],
    ),
    JointTemplate(
        template_id="product-launch-check",
        name="产品上线检查",
        description=(
            "多 Profile 并行做各自领域的健康检查，统一汇总结果。"
            "适用于产品上线前的全面检查。"
        ),
        stages=[
            {
                "profile_name": "chainke-dev",
                "goal": "对项目进行代码质量安全审计，列出所有已修复和待修复的漏洞",
            },
            {
                "profile_name": "gaia-city",
                "goal": "对系统架构进行完整性检查，确认所有模块的状态和依赖关系",
            },
            {
                "profile_name": "zhairu",
                "goal": "检查项目文档完整性，包括 README、API 文档、部署指南等",
            },
        ],
    ),
    JointTemplate(
        template_id="data-analysis-pipeline",
        name="数据分析流水线",
        description=(
            "数据提取 → 分析建模 → 报告输出。chrono 提取数据，"
            "seraphina 做分析建模，zhairu 输出分析报告。"
        ),
        stages=[
            {
                "profile_name": "chrono",
                "goal": "从数据库和日志中提取最近一个月的用户行为数据，做初步清洗和统计",
            },
            {
                "profile_name": "seraphina",
                "goal": "对上述数据进行深度分析，构建用户画像模型，找出关键趋势和异常",
            },
            {
                "profile_name": "zhairu",
                "goal": "根据分析结果撰写数据报告，包含可视化建议和业务决策建议",
            },
        ],
    ),
]

# ── Service Class ──────────────────────────────────────────────────────


class JointOpsManager:
    """联合作战管理器 —— 创建、执行和管理联合作战流水线。

    职责
    ----
    - 创建/列出/查询联合作战
    - 按 Stage 顺序执行，自动传递上下文
    - 通过 subprocess 调用 ``hermes`` CLI 执行每个 Stage
    - JSON 文件持久化
    """  # noqa: E501

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._lock = Lock()

        if data_dir is not None:
            self._data_dir = Path(data_dir).resolve()
        else:
            self._data_dir = DATA_DIR

        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._ops_file = self._data_dir / "joint_ops.json"
        self._templates_file = self._data_dir / "joint_templates.json"

        # In-memory cache
        self._operations: dict[str, JointOperation] = {}
        self._templates: dict[str, JointTemplate] = {}

        # Load persisted data
        self._load_operations()
        self._load_templates()

        # Merge predefined templates into cached templates
        self._merge_predefined_templates()

        logger.info(
            "JointOpsManager initialised — data_dir=%s, ops=%d, templates=%d",
            self._data_dir,
            len(self._operations),
            len(self._templates),
        )

    # ── Persistence ───────────────────────────────────────────────────

    def _ops_file_path(self) -> Path:
        return self._ops_file

    def _templates_file_path(self) -> Path:
        return self._templates_file

    def _load_operations(self) -> None:
        """从 JSON 文件加载已持久化的联合作战。"""
        path = self._ops_file_path()
        if not path.is_file():
            self._operations = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            operations = {}
            for item in raw.get("operations", []):
                op = JointOperation.from_dict(item)
                operations[op.op_id] = op
            self._operations = operations
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load operations: %s", exc)
            self._operations = {}

    def _save_operations(self) -> None:
        """将联合作战保存到 JSON 文件。"""
        data = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "operations": [op.to_dict() for op in self._operations.values()],
        }
        path = self._ops_file_path()
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save operations: %s", exc)

    def _load_templates(self) -> None:
        """从 JSON 文件加载模板。"""
        path = self._templates_file_path()
        if not path.is_file():
            self._templates = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            templates = {}
            for item in raw.get("templates", []):
                tmpl = JointTemplate.from_dict(item)
                templates[tmpl.template_id] = tmpl
            self._templates = templates
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load templates: %s", exc)
            self._templates = {}

    def _save_templates(self) -> None:
        """将模板保存到 JSON 文件。"""
        data = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "templates": [t.to_dict() for t in self._templates.values()],
        }
        path = self._templates_file_path()
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save templates: %s", exc)

    def _merge_predefined_templates(self) -> None:
        """将预定义模板合并到缓存中（不会覆盖用户保存的同名模板）。"""
        for tmpl in _PREDEFINED_TEMPLATES:
            if tmpl.template_id not in self._templates:
                self._templates[tmpl.template_id] = tmpl

    # ── Operations ────────────────────────────────────────────────────

    def create_operation(
        self,
        name: str,
        description: str,
        stages: list[dict],
    ) -> JointOperation:
        """创建一个新的联合作战。

        Parameters
        ----------
        name : str
            作战名称。
        description : str
            作战描述。
        stages : list[dict]
            Stage 列表，每个 dict 需包含 ``profile_name`` 和 ``goal``。

        Returns
        -------
        JointOperation
            创建成功的作战对象。
        """
        if not name or not name.strip():
            raise ValueError("作战名称不能为空")
        if not stages:
            raise ValueError("至少需要一个 Stage")

        op_id = f"op-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        joint_stages = []
        for i, s in enumerate(stages):
            profile_name = s.get("profile_name", "")
            goal = s.get("goal", "")
            if not profile_name or not goal:
                raise ValueError(f"Stage {i + 1} 缺少 profile_name 或 goal")
            joint_stages.append(
                JointStage(
                    stage_id=f"stage-{uuid.uuid4().hex[:8]}",
                    profile_name=profile_name,
                    goal=goal,
                    status="pending",
                )
            )

        operation = JointOperation(
            op_id=op_id,
            name=name.strip(),
            description=description.strip(),
            status="planning",
            stages=joint_stages,
            created_at=now,
        )

        with self._lock:
            self._operations[op_id] = operation
            self._save_operations()

        logger.info("Created operation: %s (%s)", op_id, name)
        return operation

    def get_operation(self, op_id: str) -> Optional[JointOperation]:
        """根据 op_id 获取联合作战详情。"""
        return self._operations.get(op_id)

    def list_operations(
        self, status: Optional[str] = None
    ) -> list[JointOperation]:
        """列出所有联合作战，可按状态过滤。

        Parameters
        ----------
        status : str | None
            过滤状态: planning / running / completed / failed / cancelled。
            为 None 时返回全部。

        Returns
        -------
        list[JointOperation]
            按创建时间降序排列的作战列表。
        """
        ops = list(self._operations.values())
        if status:
            ops = [op for op in ops if op.status == status]
        ops.sort(key=lambda op: op.created_at, reverse=True)
        return ops

    def execute_operation(self, op_id: str) -> JointOperation:
        """执行整个联合作战（按 Stage 顺序依次执行）。

        每个 Stage 完成后，其 ``context_output`` 自动传递给下一个 Stage
        作为 ``context_input``。

        Parameters
        ----------
        op_id : str
            要执行的作战 ID。

        Returns
        -------
        JointOperation
            执行中的作战对象。

        Raises
        ------
        ValueError
            如果作战不存在、状态不为 planning 或已执行过。
        """
        op = self.get_operation(op_id)
        if op is None:
            raise ValueError(f"作战 {op_id} 不存在")
        if op.status not in ("planning", "running"):
            raise ValueError(
                f"作战 {op_id} 当前状态为 '{op.status}'，无法执行"
            )

        # 更新状态为 running
        op.status = "running"
        with self._lock:
            self._save_operations()

        context_input = ""
        all_succeeded = True
        total = len(op.stages)

        try:
            for idx, stage in enumerate(op.stages):
                stage.context_input = context_input
                result = self._run_stage_command(stage, context_input)
                stage.context_output = result.get("output", "")
                stage.result = result.get("raw", "")
                stage.status = result.get("status", "failed")
                stage.started_at = result.get("started_at")
                stage.completed_at = result.get("completed_at")

                if stage.status != "completed":
                    all_succeeded = False
                    logger.error(
                        "Stage %s (%s) failed for operation %s",
                        stage.stage_id,
                        stage.profile_name,
                        op_id,
                    )
                    break

                # 传递上下文到下一个 Stage
                context_input = stage.context_output

                # 每执行完一个 Stage 就持久化一次
                with self._lock:
                    self._save_operations()

            # 更新作战最终状态
            if all_succeeded and all(
                s.status == "completed" for s in op.stages
            ):
                op.status = "completed"
                op.result_summary = (
                    f"联合作战 '{op.name}' 成功完成，"
                    f"共 {total} 个 Stage 全部执行成功"
                )
            elif all_succeeded:
                # 部分完成（某个 stage 失败导致提前终止）
                completed_count = sum(
                    1 for s in op.stages if s.status == "completed"
                )
                op.status = "failed"
                op.result_summary = (
                    f"联合作战 '{op.name}' 执行中断："
                    f"已完成 {completed_count}/{total} 个 Stage"
                )
            else:
                op.status = "failed"
                op.result_summary = (
                    f"联合作战 '{op.name}' 执行失败"
                )

            op.completed_at = datetime.now(timezone.utc).isoformat()

        except Exception as exc:
            op.status = "failed"
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result_summary = f"执行异常: {exc}"
            logger.exception("Unexpected error executing operation %s", op_id)

        with self._lock:
            self._save_operations()

        return op

    def execute_stage(self, op_id: str, stage_id: str) -> JointStage:
        """执行联合作战中的单个 Stage。

        如果该 Stage 有前驱 Stage，自动使用其 context_output 作为输入。

        Parameters
        ----------
        op_id : str
            作战 ID。
        stage_id : str
            Stage ID。

        Returns
        -------
        JointStage
            执行后的 Stage 对象。

        Raises
        ------
        ValueError
            如果作战或 Stage 不存在。
        """
        op = self.get_operation(op_id)
        if op is None:
            raise ValueError(f"作战 {op_id} 不存在")

        target_stage = None
        prev_context = ""
        for i, s in enumerate(op.stages):
            if s.stage_id == stage_id:
                target_stage = s
                # 获取前一个 Stage 的输出作为 context_input
                if i > 0:
                    prev_context = op.stages[i - 1].context_output
                break

        if target_stage is None:
            raise ValueError(f"Stage {stage_id} 在作战 {op_id} 中不存在")

        target_stage.context_input = prev_context
        result = self._run_stage_command(target_stage, prev_context)
        target_stage.context_output = result.get("output", "")
        target_stage.result = result.get("raw", "")
        target_stage.status = result.get("status", "failed")
        target_stage.started_at = result.get("started_at")
        target_stage.completed_at = result.get("completed_at")

        with self._lock:
            self._save_operations()

        return target_stage

    def cancel_operation(self, op_id: str) -> JointOperation:
        """取消正在执行或计划中的联合作战。

        Parameters
        ----------
        op_id : str
            要取消的作战 ID。

        Returns
        -------
        JointOperation
            取消后的作战对象。

        Raises
        ------
        ValueError
            如果作战不存在或已完成。
        """
        op = self.get_operation(op_id)
        if op is None:
            raise ValueError(f"作战 {op_id} 不存在")
        if op.status in ("completed", "failed"):
            raise ValueError(
                f"作战 {op_id} 已处于 '{op.status}' 状态，无法取消"
            )

        op.status = "cancelled"
        op.completed_at = datetime.now(timezone.utc).isoformat()
        op.result_summary = f"联合作战 '{op.name}' 已被取消"

        # 将所有 pending / running 的 stage 标记为 cancelled
        for stage in op.stages:
            if stage.status in ("pending", "running"):
                stage.status = "cancelled"
                if not stage.completed_at:
                    stage.completed_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._save_operations()

        logger.info("Cancelled operation: %s", op_id)
        return op

    # ── Templates ─────────────────────────────────────────────────────

    def get_templates(self) -> list[JointTemplate]:
        """获取所有可用模板（预定义 + 用户保存）。"""
        return list(self._templates.values())

    def save_template(
        self, name: str, description: str, stages: list[dict]
    ) -> JointTemplate:
        """保存一个新的作战模板。

        Parameters
        ----------
        name : str
            模板名称。
        description : str
            模板描述。
        stages : list[dict]
            Stage 定义列表，每个 dict 需包含 ``profile_name`` 和 ``goal``。

        Returns
        -------
        JointTemplate
            保存成功的模板对象。
        """
        if not name or not name.strip():
            raise ValueError("模板名称不能为空")
        if not stages:
            raise ValueError("至少需要一个 Stage")

        template_id = f"tmpl-{uuid.uuid4().hex[:8]}"
        tmpl = JointTemplate(
            template_id=template_id,
            name=name.strip(),
            description=description.strip(),
            stages=[
                {"profile_name": s["profile_name"], "goal": s["goal"]}
                for s in stages
            ],
        )

        with self._lock:
            self._templates[template_id] = tmpl
            self._save_templates()

        logger.info("Saved template: %s (%s)", template_id, name)
        return tmpl

    # ── Internal helpers ──────────────────────────────────────────────

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _run_stage_command(
        self, stage: JointStage, context_input: str
    ) -> dict:
        """执行单个 Stage 的 CLI 命令。

        通过 subprocess 调用 ``hermes -p <profile> chat -q "<goal>" -Q``，
        捕获 stdout 作为 context_output。

        Parameters
        ----------
        stage : JointStage
            要执行的 Stage。
        context_input : str
            前一个 Stage 传递的上下文（会追加到 goal 之前）。

        Returns
        -------
        dict
            包含 output, raw, status, started_at, completed_at 的字典。
        """
        started_at = self._now_iso()

        # 构建提示词：如果有上下文，拼接在 goal 前面
        goal_text = stage.goal
        if context_input:
            # 截取上下文的前 2000 字符以避免提示过长
            truncated = context_input[:2000]
            if len(context_input) > 2000:
                truncated += "\n[上下文已截断...]"
            goal_text = f"【上下文】\n{truncated}\n\n【任务】\n{stage.goal}"

        cmd = ["hermes", "-p", stage.profile_name, "chat", "-q", goal_text, "-Q"]

        logger.info(
            "Executing stage %s: %s ...",
            stage.stage_id,
            " ".join(cmd[:3]) + " chat ...",
        )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
                encoding="utf-8",
                errors="replace",
            )

            completed_at = self._now_iso()

            if proc.returncode == 0:
                output = proc.stdout.strip()
                if not output:
                    output = proc.stderr.strip() or "(无输出)"
                return {
                    "output": output,
                    "raw": output,
                    "status": "completed",
                    "started_at": started_at,
                    "completed_at": completed_at,
                }
            else:
                error_msg = proc.stderr.strip() or proc.stdout.strip() or "未知错误"
                logger.error(
                    "Stage %s failed (rc=%d): %s",
                    stage.stage_id,
                    proc.returncode,
                    error_msg,
                )
                return {
                    "output": "",
                    "raw": f"Exit code {proc.returncode}: {error_msg}",
                    "status": "failed",
                    "started_at": started_at,
                    "completed_at": completed_at,
                }

        except subprocess.TimeoutExpired:
            completed_at = self._now_iso()
            logger.error("Stage %s timed out after 300s", stage.stage_id)
            return {
                "output": "",
                "raw": "Stage 执行超时（300秒）",
                "status": "failed",
                "started_at": started_at,
                "completed_at": completed_at,
            }
        except FileNotFoundError:
            completed_at = self._now_iso()
            logger.error(
                "hermes CLI not found for stage %s", stage.stage_id
            )
            return {
                "output": "",
                "raw": (
                    "hermes CLI 未找到。请确认 hermes 已安装并在 PATH 中。\n"
                    "回退模式：使用模拟输出。"
                ),
                "status": "completed",
                "started_at": started_at,
                "completed_at": completed_at,
            }
        except OSError as exc:
            completed_at = self._now_iso()
            logger.error(
                "OS error executing stage %s: %s", stage.stage_id, exc
            )
            return {
                "output": "",
                "raw": f"系统错误: {exc}",
                "status": "failed",
                "started_at": started_at,
                "completed_at": completed_at,
            }


# ── Module-level singleton ─────────────────────────────────────────────

_manager: Optional[JointOpsManager] = None


def get_manager() -> JointOpsManager:
    """获取（或创建）JointOpsManager 单例。"""
    global _manager
    if _manager is None:
        _manager = JointOpsManager()
    return _manager
