import json, os

# Check chapter_plan output
plan_file = "task_outputs/chapter_plan_ch1_output.json"
if os.path.exists(plan_file):
    d = json.load(open(plan_file, "r", encoding="utf-8"))
    print(f"chapter_plan output keys: {list(d.keys())}")
    intent = d.get("chapter_intent", "")
    print(f"chapter_intent length: {len(intent)}")
    if intent:
        print(f"chapter_intent preview: {intent[:200]}")
else:
    print(f"{plan_file} NOT FOUND")

# Check intent file
intent_file = "runtime/ch0001_intent.md"
if os.path.exists(intent_file):
    with open(intent_file, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"\nintent file size: {len(content)}")
    print(f"intent preview: {content[:200]}")
