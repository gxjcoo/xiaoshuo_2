import json, glob, os, shutil, tempfile

r = "runtime"

# Count runtime files
outlines = len(glob.glob(os.path.join(r, "ch*_outline.json")))
styles = len(glob.glob(os.path.join(r, "ch*_style.txt")))
intents = len(glob.glob(os.path.join(r, "ch*_intent.md")))
generated = len(glob.glob(os.path.join(r, "ch*_generated.md")))
final = len(glob.glob(os.path.join(r, "ch*_final.md")))
entity_maps = len(glob.glob(os.path.join(r, "chapter-*.entity_map.json")))

print("=== Runtime 文件统计 ===")
print(f"  骨架抽取(outline): {outlines}/385")
print(f"  风格分析(style):   {styles}/385")
print(f"  意图规划(intent):  {intents}/385")
print(f"  正文生成(generated): {generated}/385")
print(f"  最终内容(final):   {final}/385")
print(f"  实体映射(entity_map): {entity_maps}/385")

# Load state - copy first to avoid corruption from concurrent writes
state = {}
try:
    tmp = tempfile.mktemp(suffix=".json")
    shutil.copy2("workflow_state.json", tmp)
    with open(tmp, "r", encoding="utf-8") as f:
        state = json.load(f)
    os.unlink(tmp)
except Exception as e:
    print(f"\n[WARN] 无法读取 workflow_state.json: {e}")
    print("  将只基于 runtime 文件统计显示进度")

tasks = state.get("tasks", {})
if not tasks:
    print("\n[INFO] 无法加载任务状态，仅基于 runtime 文件显示进度")
    exit(0)

print(f"\n=== 任务状态 ===")
print(f"  Overall: {state.get('status', '?')}")

status_count = {}
for k, v in tasks.items():
    s = v.get("status", "unknown")
    status_count[s] = status_count.get(s, 0) + 1
for s, c in sorted(status_count.items()):
    print(f"  {s}: {c}")

# Running tasks
running = [(k, v) for k, v in tasks.items() if v.get("status") == "running"]
print(f"\n=== 正在运行 ({len(running)}) ===")
for k, v in running[:20]:
    started = v.get("started_at", "?")
    print(f"  {k}  started: {started}")

# Latest completed
completed = sorted(
    [(k, v) for k, v in tasks.items() if v.get("status") == "completed"],
    key=lambda x: x[1].get("completed_at", ""),
    reverse=True
)[:10]
print(f"\n=== 最近完成 ({len(completed)}) ===")
for k, v in completed:
    print(f"  {k}  completed: {v.get('completed_at', '?')}")

# Failed tasks
failed = [(k, v) for k, v in tasks.items() if v.get("status") == "failed"]
print(f"\n=== 失败任务 ({len(failed)}) ===")
for k, v in failed[:10]:
    print(f"  {k}  error: {v.get('error', '?')}")
