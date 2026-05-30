import json, os

state_file = "workflow_state.json"
backup_file = "workflow_state_backup.json"

# Backup corrupted file
if not os.path.exists(backup_file):
    import shutil
    shutil.copy2(state_file, backup_file)
    print(f"Backed up corrupted file to {backup_file}")

with open(state_file, "r", encoding="utf-8") as f:
    content = f.read()

# Find last complete task entry ending with '},'
last_task_end = content.rfind('},', 0, len(content) - 100)
if last_task_end > 0:
    # Try progressively shorter truncations
    for offset in range(0, 500, 5):
        try_point = last_task_end - offset
        truncated = content[:try_point + 1]
        # Close the tasks object and top-level object
        truncated += "\n    }\n  }"
        try:
            data = json.loads(truncated)
            task_count = len(data.get("tasks", {}))
            print(f"Recovered state with {task_count} tasks at offset {offset}")
            print(f"Status: {data.get('status', '?')}")
            
            # Show task status summary
            status_count = {}
            for k, v in data.get("tasks", {}).items():
                s = v.get("status", "unknown")
                status_count[s] = status_count.get(s, 0) + 1
            print(f"Task status: {status_count}")
            
            with open("workflow_state_recovered.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("Saved to workflow_state_recovered.json")
            break
        except json.JSONDecodeError:
            continue
    else:
        print("Could not recover state file")
else:
    print("Could not find truncation point")
