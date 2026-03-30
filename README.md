To run proxy server for model request formatting and usage logging:

`uvicorn proxy:app --port 4000 &> proxy.txt`

Gemini's problem is the tools formatting. TODO: test that it can actually call tools with the new setup.

MiniMax's problem is 1) it doesn't accept the 'developer' role and if we try to map it to the 'system' role, it only expects one message with the 'system' role. 

Kimi doesn't accept 'developer' role. Changing 'developer' role to 'system' role fixes problem. 

Token usage logs are written to:

`usage_logs/usage.jsonl`

Each line stores timestamp, provider, request model, response model, status, and usage token counts.

TODO: try `codex exec`. 