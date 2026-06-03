import json, os

f = "workflow_state.json"
if not os.path.exists(f):
    print("workflow_state.json NOT FOUND")
    exit(1)

data = json.load(open(f, "r", encoding="utf-8"))
print(f"status: {data.get('status')}")
print(f"dag_node_count: {data.get('dag_node_count')}")

tasks = data.get("tasks", {})
status_count = {}
for v in tasks.values():
    s = v.get("status", "?")
    status_count[s] = status_count.get(s, 0) + 1
print(f"tasks: {len(tasks)}, distribution: {status_count}")

# Check for any errors
for k, v in tasks.items():
    if v.get("error"):
        print(f"  ERROR in {k}: {v['error']}")

# Check state file size
print(f"state file size: {os.path.getsize(f)} bytes")

# Check task_outputs
to_dir = "task_outputs"
if os.path.exists(to_dir):
    files = os.listdir(to_dir)
    print(f"task_outputs: {len(files)} files")
