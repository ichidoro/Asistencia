import json

log_file = r"C:\Users\danie\.gemini\antigravity\brain\8cac5fb3-4c42-4b62-ab2f-0c59fac8d902\.system_generated\logs\transcript.jsonl"

commands = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    args = tc.get('args') or tc.get('Arguments') or {}
                    cmd = args.get('CommandLine', '')
                    if any(kw in cmd.lower() for kw in ['delete', 'sqlite3', 'update', 'run_command', 'check_remote']):
                        commands.append(cmd)
        except Exception as e:
            pass

print(f"Total commands found: {len(commands)}")
for c in commands:
    print(c)
