"""
工作流集成测试

测试内容：
1. DAG 引擎核心功能
2. 状态持久化
3. 任务节点执行
4. 拆书功能
"""

import os
import sys
import json
import tempfile

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)


def test_dag_engine():
    """测试 DAG 引擎核心功能"""
    print("测试 DAG 引擎...")
    
    from workflow.engine import DAG
    from workflow.base import TaskNode
    
    # 创建测试节点
    class TestNodeA(TaskNode):
        @property
        def id(self): return "a"
        @property
        def name(self): return "节点A"
        def execute(self, context): return {"a_result": "done"}
    
    class TestNodeB(TaskNode):
        @property
        def id(self): return "b"
        @property
        def name(self): return "节点B"
        @property
        def deps(self): return ["a"]
        def execute(self, context): return {"b_result": context.get("a_result", "") + " processed"}
    
    # 构建 DAG
    dag = DAG()
    dag.add_node(TestNodeA())
    dag.add_node(TestNodeB())
    
    # 验证
    errors = dag.validate()
    assert not errors, f"DAG 验证失败: {errors}"
    
    # 拓扑排序
    order = dag.topological_sort()
    assert order == ["a", "b"], f"拓扑排序错误: {order}"
    
    print("  DAG 引擎测试通过")


def test_state_store():
    """测试状态持久化"""
    print("测试状态存储...")
    
    from workflow.state import StateStore
    
    # 使用临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_file = f.name
    
    try:
        state = StateStore(state_file)
        
        # 创建新运行
        run_id = state.create_new_run({"test": "data"})
        assert run_id, "创建运行失败"
        
        # 更新任务状态
        state.update_task_status("task1", "running")
        state.update_task_status("task1", "completed", outputs={"result": "ok"})
        
        # 验证
        assert state.get_task_status("task1") == "completed"
        assert state.get_task_outputs("task1") == {"result": "ok"}
        
        # 设置上下文
        state.set_context("key1", "value1")
        assert state.get_context("key1") == "value1"
        
        # 重新加载
        state2 = StateStore(state_file)
        state2.load_existing_run()
        assert state2.get_task_status("task1") == "completed"
        
        print("  状态存储测试通过")
    finally:
        os.unlink(state_file)


def test_progress_tracker():
    """测试进度追踪器"""
    print("测试进度追踪器...")
    
    from workflow.progress import ProgressTracker
    
    tracker = ProgressTracker()
    
    # 测试无 rich 库的情况
    tracker.start_workflow(3)
    tracker.start_task("task1", "任务1")
    tracker.complete_task("task1", success=True)
    tracker.skip_task("task2", "已完成")
    tracker.fail_task("task3", "测试错误")
    tracker.stop_workflow()
    
    print("  进度追踪器测试通过")


def test_task_nodes():
    """测试任务节点定义"""
    print("测试任务节点...")
    
    from workflow.tasks import (
        SplitNovelTask,
        DecomposeBookTask,
        InjectProfileTask,
        StyleAnalysisTask,
        OutlineExtractTask,
        EntityRewriteTask,
        ChapterPlanTask,
        ContentGenerateTask,
        AuditReviseTask,
        ContinuityCheckTask,
        ForeshadowManagerTask,
        StyleConsistencyTask,
        WriteOutputTask,
        UpdateContextTask
    )
    
    # 验证所有节点都可以实例化
    nodes = [
        SplitNovelTask(),
        DecomposeBookTask(),
        InjectProfileTask(),
        StyleAnalysisTask(),
        OutlineExtractTask(),
        EntityRewriteTask(),
        ChapterPlanTask(),
        ContentGenerateTask(),
        AuditReviseTask(),
        ContinuityCheckTask(),
        ForeshadowManagerTask(),
        StyleConsistencyTask(),
        WriteOutputTask(),
        UpdateContextTask()
    ]
    
    for node in nodes:
        assert node.id, f"节点缺少 id"
        assert node.name, f"节点 {node.id} 缺少 name"
    
    print("  任务节点测试通过")


def test_dag_builder():
    """测试 DAG 构建器"""
    print("测试 DAG 构建器...")
    
    from workflow.dag_builder import build_chapter_dag, build_full_dag, print_dag_structure
    
    # 测试单章 DAG
    dag = build_chapter_dag(chapter_number=1)
    errors = dag.validate()
    assert not errors, f"单章 DAG 验证失败: {errors}"
    
    # 测试完整 DAG
    dag = build_full_dag(start_chapter=1, end_chapter=3)
    errors = dag.validate()
    assert not errors, f"完整 DAG 验证失败: {errors}"
    
    # 测试 DAG 结构输出
    print_dag_structure()
    
    print("  DAG 构建器测试通过")


def test_cli_import():
    """测试 CLI 导入"""
    print("测试 CLI 导入...")
    
    from workflow.cli import create_parser, main
    
    parser = create_parser()
    assert parser, "创建解析器失败"
    
    print("  CLI 导入测试通过")


def test_workflow_engine():
    """测试工作流引擎"""
    print("测试工作流引擎...")
    
    from workflow.engine import DAG, WorkflowEngine
    from workflow.base import TaskNode
    
    # 创建简单的测试 DAG
    class SimpleTask(TaskNode):
        @property
        def id(self): return "simple"
        @property
        def name(self): return "简单任务"
        def execute(self, context): 
            print(f"    执行简单任务，上下文: {context}")
            return {"simple_result": "done"}
    
    dag = DAG()
    dag.add_node(SimpleTask())
    
    # 使用临时状态文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_file = f.name
    
    try:
        engine = WorkflowEngine(dag, state_file=state_file)
        engine.context = {"test_key": "test_value"}
        
        # 执行
        summary = engine.run(resume=False)
        
        assert summary.get("status") == "completed", f"执行失败: {summary}"
        
        print("  工作流引擎测试通过")
    finally:
        os.unlink(state_file)


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始工作流集成测试")
    print("=" * 50)
    
    tests = [
        test_dag_engine,
        test_state_store,
        test_progress_tracker,
        test_task_nodes,
        test_dag_builder,
        test_cli_import,
        test_workflow_engine
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  测试失败: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
